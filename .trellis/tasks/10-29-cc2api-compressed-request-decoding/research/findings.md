# Research: 压缩请求的严格编解码 API 与资源边界

- Query: 不增加依赖，如何严格、有界解码请求，并在现有正文策略／身份／CCH 改写后按入站编码重新编码？
- Scope: mixed；仅依赖与输入边界，入口／账号／具体端点由主会话研究。
- Date: 2026-10-29

## Findings

### 文件与版本证据

| 文件 | 结论 |
| --- | --- |
| `cc2api/Cargo.toml:78` | 已有直接依赖 flate2、brotli、zstd，无需更改 manifest／lock。 |
| `cc2api/Cargo.lock:582`、`:1305` | flate2 **1.1.9**，实际后端 miniz_oxide **0.8.9**。 |
| `cc2api/Cargo.lock:223`、`:234` | brotli **3.5.0**，brotli-decompressor **2.5.1**。 |
| `cc2api/Cargo.lock:3514`、`:3523`、`:3533` | zstd **0.12.4**、zstd-safe **6.0.6**、zstd-sys **2.0.16+zstd.1.5.7**。 |
| `cc2api/src/service/gateway.rs:3757` | 现有响应解码：反向遍历编码链，但输出无上限；`:3803` 只读单个 gzip member，`:3816` 未知编码透传，`:3820` zlib 失败再试 raw。不能直接用于严格入站。 |
| `cc2api/src/service/gateway.rs:1579`、`:1786` | 两处既有请求读取上限均为 `10 * 1024 * 1024`。 |
| `cc2api/target/debug/deps/{flate2,brotli,zstd}-*.d` | 产物指向上述确切版本的 registry 源码；实验直接链接已有 `.rlib`，未运行 Cargo 或改产品文件。 |

下文依赖相对路径均基于 `/root/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/`，行号对应当前本机实际源码。

### 严格解码：支持范围及可复用 API

- **gzip／x-gzip**：`flate2::bufread::MultiGzDecoder::new(body: &[u8])`，通过 `Read` 读取。`flate2-1.1.9/src/gz/bufread.rs:281` 校验每个 member 的 CRC32／ISIZE，`:311` 继续后续 member，`:401` 是公开构造器。合法多 member 要拼接所有明文；损坏第二 member、截断、垃圾／零填充尾巴均拒绝。普通 `read::GzDecoder` 会忽略后续 member／尾巴。[版本化官方 API](https://docs.rs/flate2/1.1.9/flate2/bufread/struct.MultiGzDecoder.html)。
- **deflate**：保留 zlib + raw 兼容，但使用 `flate2::Decompress::new(zlib_header: bool)`、`decompress(input, output, FlushDecompress::None) -> Result<Status, DecompressError>`、`total_in()`／`total_out()`。来源：`flate2-1.1.9/src/mem.rs:403`、`:452`、`:484`。分块输出，只有 **`Status::StreamEnd` 且全部输入已消耗** 才成功；无输入／输出进展却未结束为截断；输出超限立即结束。`StreamEnd` 对 zlib 还确认 Adler32（`:184`）。先严格验证 zlib，格式失败才按同样规则尝试 raw；超限不能重新回退尝试。不能用普通 ZlibDecoder／DeflateDecoder 的 EOF 证明完整：`src/zio.rs:151` 将 EOF 时的 BufError 也返回成成功读取。
- **br**：标准 Brotli，使用 `brotli::{BrotliState, HeapAlloc, HuffmanCode, BrotliDecompressStream, BrotliResult}`；公开重导出在 `brotli-3.5.0/src/lib.rs:26`、`:38`、`:69`。`BrotliState::new_strict(alloc_u8, alloc_u32, alloc_hc)` 禁用 large-window 扩展（`brotli-decompressor-2.5.1/src/state.rs:409`）。`BrotliDecompressStream(&mut available_in, &mut input_offset, input, &mut available_out, &mut output_offset, output, &mut total_out, &mut state) -> BrotliResult` 在 `src/decode.rs:2641`。仅 `ResultSuccess` 且 `available_in == 0`／`input_offset == body.len()` 才成功；NeedsMoreInput 为截断，ResultFailure 为损坏，NeedsMoreOutput 继续有界输出。普通 `Decompressor::new(...).read_to_end()` 首次 EOF 可能吞掉尾随输入；`:335` 的额外读取语义及 `src/reader.rs:355` 的库内测试都证实此点，不宜仅检查底层 slice 是否为空。
- **zstd**：`zstd::stream::read::Decoder::with_buffer(body: &[u8]) -> io::Result<Self>`，**第一次读取前**调用 `window_log_max(24) -> io::Result<()>`，再有界读取到 EOF；默认支持连续 frame，不能调用 `single_frame()`。API：`zstd-0.12.4/src/stream/read/mod.rs:35`、`:49`；窗口 setter 在 `src/stream/mod.rs:34`，完整帧判断在 `src/stream/raw.rs:211`。`finish(self) -> R` 只取回 reader，**不替代末尾校验**。标准 skippable frame 可接受并跳过；不是尾随垃圾。[RFC 8878 §3.1](https://www.rfc-editor.org/rfc/rfc8878.html#section-3.1)。

建议纯编解码模块只处理字节与编码链，不解析 JSON、不按 Claude Code 版本开关。调用方在解码后执行既有策略／改写，然后交回最终字节重编码。

### 大小、窗口、层数与 CPU

- 入站原字节及**每层解码输出**保留 **10 MiB**；最多 **4 个非 identity 编码层**。这两个新层级约束是资源策略，不能表述为接受任何层数／任意中间大小的合法编码链。
- 对 MultiGzDecoder／zstd 可用 `(&mut decoder).take(limit + 1).read_to_end(&mut out)`，`out.len() > limit` 就拒绝。恰好等于 limit 的合法流仍须读完尾部校验；只 `take(limit)` 会漏掉 CRC。deflate／br 使用上述流状态 API，每次只给不超过剩余 `limit+1` 的小输出块。
- `take(limit+1)` 限的是向外返回的字节数；`Vec.capacity()`、解码器窗口和工作区另占内存，不是请求总内存硬限额。
- zstd `window_log_max(24)` 限窗口为 **16 MiB**，不是总分配 16 MiB。底层默认为 27，即 128 MiB：`zstd-sys-2.0.16+zstd.1.5.7/zstd/lib/zstd.h:1287`；`:646` 说明 streaming 限制。底层先检查窗口再分配：`zstd/lib/decompress/zstd_decompress.c:2231`。该限制也适用于后续 frame。
- **已发现的兼容边界**：11 字节、32 MiB 窗口、2 字节输出的合法 zstd 流，默认能解，24-bit 上限拒绝；25-bit large-window Brotli 扩展流，普通 reader 接受、strict 拒绝。标准 br 的窗口范围在 `brotli-decompressor-2.5.1/src/decode.rs:152`；这些拒绝应在支持范围中明确，而非称数据损坏。4 层上限同样会排除更多层的合法编码链。限制以内的普通样本未发现矛盾。
- **CPU 实证**：4096 个空 gzip member 共 81,920 字节、输出 0；4096 个空 zstd skippable frame 共 32,768 字节、输出 0。二者均会执行成员／帧处理而不触发输出上限；本机 debug 产物单次约 122 ms／0.9 ms，仅为观测。输入／输出／层数／窗口限制不等于可取消的 CPU 超时；外包 async timeout 不能中断同步 reader。本研究不建议引入全局并发框架。

### Content-Encoding 解析与顺序

1. 从原始 `HeaderMap.get_all(CONTENT_ENCODING)` 按多值顺序读取；每值按逗号拆分，仅去掉两端 SP／HTAB，非空项按 ASCII 大小写无关匹配。编码按声明正序施加、**逆序解码**。例如两行 `gzip`、`br` 等价 `gzip, br`：先 br 解码，再 gzip。[RFC 9110 §8.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.4)。
2. `identity` 兼容为 no-op，不计实际编码层数；空头／合理数量的空列表项忽略。RFC 的 `#list` 要求接收端容忍合理数量空项，不能将每个 `gzip,,` 一概判错；另给列表片段（含空／identity）设小上限，例如 32，避免无效项绕过层数预算。[§5.6.1.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.1.2)。
3. 非空项必须完整满足 token 语法；引号、`;q=...`、内部空白、非 ASCII／不可转换值拒绝为 400，不能沿用 response helper 的 `filter_map(to_str().ok())` 静默丢弃。合法但未知 token（包括 `*`、compress 等未实现编码）415；超 4 个有效层建议 415。先验证整条链，再开始解码。[§5.6.2–5.6.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.2)。
4. `Accept-Encoding` 表达协商偏好，**不能**据此判断当前请求 body 是否压缩；无 Content-Encoding 时不嗅探 magic 或改变旧路径。

### 改写后按原编码链重编码（最新用户决定）

- 顺序是：**解码 → 现有正文策略／身份／Session／CCH → 得到最终 JSON 字节 → 正序 encode**。例如 `gzip, br`：最终 JSON 先 gzip、再 br；不得在 CCH 完成后再改 JSON 字节。此边界的具体 Rewriter 调用位置由主会话核对。
- 可直接使用的 encoder（全部已有依赖）：
  - gzip／x-gzip：`flate2::write::GzEncoder::new(writer, Compression)` → `write_all` → `finish(self) -> io::Result<W>`；`flate2-1.1.9/src/gz/write.rs:57`、`:125`。
  - deflate：`flate2::write::ZlibEncoder::new(writer, Compression)` → `write_all` → `finish`；`src/zlib/write.rs:41`、`:123`。入站 raw 兼容不要求原样容器出站，声明 deflate 时统一标准 zlib。[RFC 9110 §8.4.1.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.4.1.2)。
  - br：`brotli::CompressorReader::new(reader, buffer_size: usize, q: u32, lgwin: u32)` → `read_to_end`（`brotli-3.5.0/src/enc/reader.rs:78`），或 `BrotliCompress(&mut reader, &mut writer, &BrotliEncoderParams) -> io::Result<usize>`（`src/enc/mod.rs:146`）。实验使用 q=4、lgwin=22。**不要依赖 CompressorWriter::into_inner 传播 finish 错误**：`src/enc/writer.rs:229` 会忽略其错误。
  - zstd：`zstd::stream::encode_all(reader, level: i32) -> io::Result<Vec<u8>>`（`zstd-0.12.4/src/stream/functions.rs:32`），或 `write::Encoder::new(writer, level)?` → `finish()?`（`src/stream/write/mod.rs:174`、`:256`）；实验 level=1。
- 建议输出保留原有效编码链顺序，ASCII token 可统一小写，忽略 identity／空项。`x-gzip` **保留别名 token**并用 gzip encoder，最少改变客户端表达；gzip 容器参数／多 member 数量／压缩字节不承诺保留。[别名语义](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.4.1.3)。
- `Content-Encoding` 对应最终编码链；旧 Content-Length／Transfer-Encoding 不能复用，Content-Length 必须使用**最终压缩字节数**，或交给现有 HTTP client 依据最终 body 构造长度。
- **编码输出上限建议**：不要直接复用入站／解码的 10 MiB，否则接近上限的不可压缩正文会因容器开销误拒绝。1024 字节合成噪声实测输出 gzip 1047、zlib 1035、br 1028、zstd 1033。最小范围方案是本次不额外增加“编码结果超过 10 MiB”的拒绝；若必须另设编码硬上限，应依据**改写后 JSON 长度**、链上各 encoder 的上界递推并留容器余量，单独定义资源预算，不能直接沿用原请求长度。`zstd::zstd_safe::compress_bound(usize)` 可用（zstd-safe `src/lib.rs:203`，zstd `src/lib.rs:25` 重导出），Brotli 有 `enc::encode::BrotliEncoderMaxCompressedSize(usize)`（`:1325`）；flate2 当前公开接口未找到 compress_bound。不能未经证明把任意固定 16／20 MiB 写成所有参数／4 层均不会误拒的保证。近 10 MiB 的不可压缩正文及重编码膨胀应纳入实施验证。

### 最小错误矩阵与回归点

| 输入／条件 | 建议结果与关键断言 |
| --- | --- |
| 无编码、空列表、identity；只有 Accept-Encoding | 保持既有正文行为；不按响应协商头误解码。 |
| gzip／x-gzip／zlib-deflate／raw-deflate／标准 br／zstd | 等价明文进入既有策略；改写后按原链编码；上游解码后核对最终 JSON／CCH。 |
| 大小写＋OWS＋重复头＋叠加／重复编码 | 逆序解码、正序编码；不能只取第一个字段。 |
| gzip 多 member／zstd 多 frame | 拼接全部明文；第二 member／frame 的损坏也拒绝；br／deflate 第二流按尾随输入拒绝。 |
| 截断、CRC／ISIZE／Adler／可选 zstd checksum 损坏、尾随垃圾 | 400，可解析 error object；不得尝试使用部分解码内容。 |
| 非法 header token／不可转换值 | 400；未知但合法的 coding／超过有效层数上限建议 415。 |
| 入站原字节或任一层输出 >10 MiB | 413；恰好 10 MiB 可用，`limit+1` 拒绝；中间层也检查。 |
| zstd 窗口超限／br large-window 扩展 | 明确拒绝并说明支持限制；不靠 `io::ErrorKind::Other` 或错误字符串稳定识别成某种细分错误。 |
| 接近 10 MiB 的合法输入被改写并重新编码 | 容许容器小幅膨胀；最终 Content-Length 等于最终编码字节数；不能因套用旧大小而误拒。 |
| 任何入站拒绝 | 调用方必须在账号分配／额度消耗／上游发送前完成；用真实入口证明零上游，依赖实验不能替代此验收。 |

### 已验证与规范来源

- **实际实验**：`probe-results.json` 持久化脱敏数字。95 行观测、113 种截断前缀；五种格式的 exact-limit／limit+1／10 MiB+1，CRC／ISIZE／Adler／zstd checksum，gzip 分成员及第二成员损坏，br 尾随／large-window，zstd 第二帧窗口限制、skippable frame，四层 encode→decode 和各 encoder 噪声往返。关键预期断言通过；普通 reader 接受损坏输入的观测是刻意暴露问题。
- **仅源码／官方文档核对**：完整 header grammar／空列表语义，所有未单独枚举的编码畸形组合，encoder 的大小上界 API；本轮没有 Gateway／账号／CCH 集成测试。不能声称已证明所有恶意输入组合或生产 CPU 时限。
- 临时实验在 `/tmp/cc2api-r3-03-decoding-research-9_5q52yn/`：`probe.rs`、`results.tsv`、`build-command.json`；rustc 1.96.0，直接使用现有 debug artifact，未运行真实账号／推理。
- 相关规范：`.trellis/workflow.md` 的 Phase 1.2；`.trellis/spec/cc2api/backend/index.md`、`service-architecture.md:27`（正文／改写时序）、`testing-quality.md`（可解析错误、大小上限、敏感边界）；`.trellis/spec/cc2api/protocol/index.md`（CCH 在最终 body 上验证）。

## Caveats / Not Found

- zlib／raw 在字节层面可能二义；严格完整 raw 校验只能证明它是有效 raw 流，不能证明发送方原意是 raw。不要用两个 magic 字节或“reader 读到 EOF”代替完整流验证；本轮未穷尽二义格式。
- raw DEFLATE／Brotli 没有通用内容 checksum，zstd checksum 可选；“严格”指格式、完整结束、输入耗尽及明确资源限制，并不保证发现每次仍能形成另一条合法流的字节修改。
- 研究覆盖通用编解码，不新增设置／依赖／并发框架，不改变 task 状态、产品、测试或 Spec，不覆盖冻结研究；具体入口范围及现有错误体映射仍由主会话收敛。
