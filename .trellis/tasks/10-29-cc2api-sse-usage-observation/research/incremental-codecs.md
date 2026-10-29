# Research: 压缩响应的同步增量观察接口

- Query: 在现有 flate2 1.1.9、brotli 3.5.0／brotli-decompressor 2.5.1、zstd 0.12.4 中，如何分块解码 gzip／x-gzip、zlib／raw deflate、br、zstd 与有序编码链，立即观察 SSE，并校验结束和限制工作区？
- Scope: mixed；本地依赖源码与最小离线探针为主，官方版本文档为补充。仅研究 codec 与观察器接口；SSE 事件规则、Gateway 完成／取消生命周期由主会话负责。
- Date: 2026-10-29

## Findings

### 结论与建议

可以直接实现同步观察，无需新增依赖、后台线程或队列。推荐持久递归的解码链：gzip 使用 `flate2::write::MultiGzDecoder<W>`；deflate 使用 `flate2::Decompress`；br 使用 `BrotliState::new_strict` 加 `BrotliDecompressStream`；zstd 使用 `zstd::stream::raw::Decoder` 加 `Operation::run_on_buffers`。每次产生的小块立即交给下一层，末端直接进入同一事件／JSON 解析器。

建议最多 **4 个非 identity 编码层**，deflate／br／zstd 每层输出块 **8 KiB**；gzip 库内输出暂存为 **32 KiB**，其持久下游 writer 再按 8 KiB 片段递归喂下一层。每层禁止用 `Vec<u8>` 作为整段输出 sink。只给库一个固定 scratch，随后又把输出持续追加进 Vec，仍然会缓存整条长响应。

br 严格标准窗口最大为 16 MiB；zstd 在首个输入前设置 `DParameter::WindowLogMax(24)`，限制所有 frame 的窗口为 16 MiB。这两个窗口值均不是该 codec 总分配或进程 RSS 上限。两个独立观察器、每个 4 层时，极端全 br 链的 codec 工作区估算约 **160 MiB**，另加两份解析缓冲、容器和分配器开销；应在 Brief 中明确，不声称“整体只用 16 MiB”。

**deflate 兼容边界必须写进设计／Brief**：两字节合法 zlib 头分流可支持普通 zlib 和普通 raw 长流，但不能无条件等价于旧有“完整尝试 zlib，任意失败后从头重试 raw”。本轮已构造合法 raw 与 zlib 头碰撞反例。最简方案对碰撞或晚期 zlib 失败保守保留已知摘要并标 partial；可选有限早期回退见下文。

### 文件与版本证据

| 文件 | 用途／结论 |
| --- | --- |
| `cc2api/Cargo.toml:78` | 现有直接依赖 flate2／brotli／zstd，不需要修改 manifest 或 lock。 |
| `cc2api/Cargo.lock:582`、`:234`、`:3514`、`:3523`、`:3533` | 分别锁定 flate2 1.1.9、brotli-decompressor 2.5.1、zstd 0.12.4、zstd-safe 6.0.6、zstd-sys 2.0.16+zstd.1.5.7；brotli 3.5.0 在 `:223`。 |
| `cc2api/src/service/usage.rs:21`、`:106`、`:156`、`:377` | 现有 UsageCapture；observe 处理逻辑字节，observe_encoded／decode_usage_body 以整包方式限长解码。 |
| `cc2api/src/service/usage.rs:316`、`:345`、`:361` | 同步生成摘要或完整记录；异步写库另由 finish 负责。codec 不应改变这些外部职责。 |
| `cc2api/src/service/diagnostics.rs:221`、`:322`、`:367` | AttemptTrace 独立持有 UsageCapture、压缩 Vec 和截断状态；当前结束后才解码，并同步决定根诊断终态。 |
| `.trellis/tasks/10-29-cc2api-compressed-request-decoding/research/findings.md` | 复用版本、严格结束、窗口和整包实验结论；其请求阻塞 worker／整包回退策略不适用于长 SSE。 |
| `.trellis/tasks/10-29-cc2api-sse-usage-observation/research/incremental-codecs-probe.rs` | 本轮离线 API 探针；只计数解码输出，不保留整个解码结果。 |

以下依赖路径统一以 `REG = /root/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/` 为根；所有文件行号来自本机该版本源码。

### gzip／x-gzip：使用现成的多成员 Write 解码器

**实际 API，源码确认：**

- `flate2::write::MultiGzDecoder<W: Write>`：`new(w: W) -> Self`、`write(&mut self, &[u8]) -> io::Result<usize>`、`flush(&mut self) -> io::Result<()>`、`get_mut(&mut self) -> &mut W`、`try_finish(&mut self) -> io::Result<()>`、`finish(self) -> io::Result<W>`。分别见 `REG/flate2-1.1.9/src/gz/write.rs:373`、`:380`、`:443`、`:462`、`:400`、`:419`、`:438`。版本化官方文档同样说明连续 member 与 Write 接口：[flate2 MultiGzDecoder 1.1.9](https://docs.rs/flate2/1.1.9/flate2/write/struct.MultiGzDecoder.html)。
- 单 member 的 `GzDecoder::finish_and_check_crc` 先完成内部输出，再检查 8 字节 footer 的 CRC32 与 ISIZE，见 `src/gz/write.rs:290`。MultiGzDecoder 在当前 member 返回零消费、还存在后续输入时，先 `try_finish()` 校验，再创建下一 member，见 `:448`；最后一个 member 要在 HTTP EOF 明确 `try_finish()`。
- 不能把每个网络 chunk 当 EOF：每次 feed 用 `write_all(part)`，随后 `flush()`，只在最终检查调用 `try_finish()`。底层 Writer 在成功 write 后可能暂存刚产生的输出；显式 flush 让本次已产生的正文立即抵达解析器，见 `src/zio.rs:213`、`:243`、`:262`。
- 内部 Writer 为 `Vec::with_capacity(32 * 1024)`，`decompress_vec` 只使用既有空余容量，不自动扩充它，见 `src/zio.rs:164`、`src/mem.rs:510`。该内部 Vec 是固定工作缓冲；传入的 W 仍必须是立即消费数据的下游。
- gzip 可变头不是无限累积：FEXTRA 长度为 u16；文件名与注释分别最多 65535 个非 NUL 字节，见 `src/gz/mod.rs:20`、`:153`、`:250`；头部 FHCRC 也校验，见 `:201`。无需自行重写 gzip framing／CRC。
- 当前 miniz 后端不能调用 `Decompress::new_gzip`：它受 `#[cfg(feature = "any_zlib")]` 保护，见 `src/mem.rs:430`。使用上述现有 Write 封装最简单。

**实测：** 1／7／1024 字节输入块均解出 2,162,688 字节；在 EOF 前输出；1024 字节输入时出口最大一次 write 为 32768 字节。两个成员输出拼接；最后成员／第二成员 CRC 错、截断 footer、截断 payload、1 字节尾垃圾、长尾垃圾和零尾巴均失败。CRC 失败前已经观察到的正文仍可能完整输出，这些摘要必须保留且 partial。

### deflate：低层状态结束检查与有限前缀分流

**实际 API，源码确认：**

```rust
Decompress::new(zlib_header: bool) -> Decompress
Decompress::decompress(&mut self, input: &[u8], output: &mut [u8],
                      flush: FlushDecompress) -> Result<Status, DecompressError>
Decompress::total_in(&self) -> u64
Decompress::total_out(&self) -> u64
Decompress::reset(&mut self, zlib_header: bool)
```

见 `REG/flate2-1.1.9/src/mem.rs:403`、`:484`、`:452`、`:458`、`:574`。`Status::StreamEnd` 为完整结束；zlib 模式还校验 Adler32，见 `:184`。用调用前后 total_in／total_out 差值计算消费和输出，固定 8 KiB 输出，喂出后复用。

feed 使用 `FlushDecompress::None`。有剩余输入或输出块已满时继续；零输入仍可能排出内部缓存。没有输入时、未结束且无消费／输出进展只表示等待；HTTP EOF 时同样状态表示截断。不要把 BufError 或读到零字节当成完整结束。对 `Finish` 的公开文档假定输出足以容纳余下数据（`src/mem.rs:467`），这里可以完全用 None 排空并根据 StreamEnd 检查，探针已验证。

StreamEnd 后当前块剩余字节／未来非空块均是尾随内容；deflate 不按 gzip 规则自动接受第二条流。普通 Read 解码器的宽松 EOF 不能代替这个检查，见 `src/zio.rs:151`。

**推荐分流：**

1. 只暂存最初两个字节。若 CM=8、CINFO<=7 且 `(CMF * 256 + FLG) % 31 == 0`，选择 zlib，否则选 raw；FDICT 不能直接当 raw，应进入 zlib 后按不支持字典处理。真实头检查见 `REG/miniz_oxide-0.8.9/src/inflate/core.rs:568`。
2. 选定后立刻流式输出，正常两种格式均支持任意长响应；EOF 要完整结束并耗尽输入。
3. **最简边界**：被分到 zlib 的流若之后失败，不从已消费的历史原字节重新试 raw；标 decode_error／partial，保留前面完成事件的已知 usage。不能继续把这种结果称为严格完整。
4. **可选小改进**：只在该层尚未输出任何字节时，最多保留例如 64 字节前缀；zlib 在这个有限范围内失败可用新 raw 状态重放这些字节。超过前缀预算或有过该层输出就锁定选择。这样下游状态尚未修改，不需要克隆整个链；晚期失败仍是 partial。64 是建议策略值，本轮没有实现／实测该分流器。

**真实反例，实测：** raw stored block 为 `78 9c 00 63 ff` + 156 个 ASCII A + `01 00 00 ff ff`。它是合法 raw，输出 156 字节；其 `78 9c` 又是合法 zlib 头，zlib 解码失败。因此仅嗅探两个字节不足以证明“原流一定是 zlib”。本轮普通 zlib／raw 1／7／1024 分块均正常输出长正文，并检查了 Adler 损坏、截断、尾随输入。

**双摘要候选的成本：** 若 deflate 就是贴近 SSE 的最内层，可同时跑两份 Decompress 与两份有界解析摘要，最终优先选择完整 zlib，否则完整 raw；无需保留长原文。若其后还有 br／gzip／zstd 等解码层，候选输出不同，后续解码状态也必须各有一份；多个 deflate 会产生分支（4 个二义层最多 16 个末端候选）。这会放大 parser 和 codec 窗口分配，不能表述为“只多一份小摘要”；本任务不推荐引入通用分支树。

### br：严格标准流与固定输出块

**实际类型／函数，源码确认：**

```rust
BrotliState<HeapAlloc<u8>, HeapAlloc<u32>, HeapAlloc<HuffmanCode>>
BrotliState::new_strict(alloc_u8, alloc_u32, alloc_hc)
BrotliDecompressStream(
    available_in: &mut usize, input_offset: &mut usize, input: &[u8],
    available_out: &mut usize, output_offset: &mut usize, output: &mut [u8],
    total_out: &mut usize, state: &mut BrotliState<...>
) -> BrotliResult
```

`brotli` 已重导出这些类型／函数，见 `REG/brotli-3.5.0/src/lib.rs:23`、`:26`、`:38`、`:69`。new_strict 在 `REG/brotli-decompressor-2.5.1/src/state.rs:409`，流函数在 `src/decode.rs:2641`。

- 每次调用重设 8 KiB output 的 offset／available；输入 offset 在同一输入片段内累计；输出立即递归喂下游。
- NeedsMoreOutput 继续；NeedsMoreInput 暂停等待，HTTP EOF 时仍是此状态则截断；ResultFailure 停止该观察器；只有 ResultSuccess 且本片段无剩余输入、未来也无非空输入才是严格成功。结束分支将未用输入还给调用方，见 `src/decode.rs:3207`。第二条 br 流为尾随内容。
- 持久 state 内部已经保留少量跨调用输入（最多 8 字节的 buffer），调用方无需缓存历史压缩体，见 `src/decode.rs:2656`、`:2744`。每个输入也切小块，避免该 API 对 >=2^32 输入／offset 的参数拒绝（`:2661`）。
- 普通 `DecompressorWriter` 使用 `new_with_custom_dictionary` 创建允许 large-window 的 state，且 flush 只 flush 下游（`src/writer.rs:242`、`:250`、`:369`）。低层 strict state 更容易明确窗口与结束；不要误用普通 writer 声称限制了标准窗口。

窗口位来自标准 WBITS，最大 24，见 `src/decode.rs:152`；strict 拒绝 large-window 扩展。[RFC 7932 §9.1](https://www.rfc-editor.org/rfc/rfc7932.html#section-9.1) 描述标准头。ring buffer 至多 `2^24 + 42 + 24` 字节（窗口、写前余量和最长字典词），见 `src/decode.rs:1810`。三组 Huffman 表各至多 256×1080 个 4 字节元素，另有固定表和小型 context map，见 `src/huffman/mod.rs:25`、`:28`、`:61`，`src/decode.rs:1284`、`:2817`、`:3031`、`:3058`、`:3067`。按每层约 20 MiB 留预算合理；它是基于源码的保守工作区估算，未做进程分配峰值测量。按 metablock 清理表，见 `src/state.rs:448`，内存不随整条 SSE 长度持续增加。

**实测：** 三种分块解出相同长度长正文；1／7 字节分块在 EOF 前输出；截断、尾垃圾和第二条 br 流不能严格成功。标准窗口／large-window 的先前整包反例结论已复用，未重复扩展组合。

### zstd：raw Decoder，保留完整 frame 边界状态

**实际 API，源码确认：**

```rust
zstd::stream::raw::Decoder::new() -> io::Result<Decoder<'static>>
Decoder::set_parameter(&mut self, parameter: DParameter) -> io::Result<()>
Operation::run_on_buffers(&mut self, input: &[u8], output: &mut [u8])
    -> io::Result<Status>
Status { remaining: usize, bytes_read: usize, bytes_written: usize }
```

见 `REG/zstd-0.12.4/src/stream/raw.rs:9`、`:34`、`:117`、`:137`、`:168`。调用例为 `decoder.set_parameter(DParameter::WindowLogMax(24))?`。run_on_buffers 来自 `Operation` trait，实施时必须显式导入；raw Decoder 没有直接的 `window_log_max` 便利方法。便利方法属于 read／write wrappers（`src/stream/mod.rs:34`）。

- 每次输入按 bytes_read 前移，输出按 bytes_written 立即递交；输出已满时，即使输入耗尽，也继续提供空输入排出尚存输出。
- **remaining==0 表示一个 frame 已完整解码且输出排空**。若本片段还有输入，继续处理下一 frame；连续 frame 和 skippable frame 均支持。本轮直接复用同一个 raw Decoder 已验证，无需在正常 frame 间重建 context。
- 保存“最后一次有效处理位于完整 frame 边界”的布尔量。正常 EOF 时它必须为 true；有未完成 frame 则空输入排空后仍须检查。若已在完整边界，不要额外 run 空输入后把新 frame 的提示值误记为截断。
- `Operation::finish(output, finished_frame)` 只根据调用方传来的布尔量检查，不会独立证明完整性，见 `src/stream/raw.rs:211`；read::Decoder::finish 也只是取回输入 reader。必须自行保存 run 返回的边界。
- 普通 `stream::write::Decoder::into_inner` 只是取回 W，没有结束校验，见 `src/stream/write/mod.rs:351`；flush 也不能代替上述检查。raw 接口更直接。
- 首次 run 前设置 WindowLogMax(24)，后续 frame 也受它限制。底层在分配缓冲前比较窗口，见 `REG/zstd-sys-2.0.16+zstd.1.5.7/zstd/lib/decompress/zstd_decompress.c:2231`。底层说明 remaining、输入／输出 pos 与错误状态的合同见同版本 `zstd/lib/zstd.h:926`。
- 遇到解码错误后禁用该状态，不再 run／flush；zstd C 文档明确错误后状态可能不可继续，须先 reset（同一 `zstd.h:942`）。本设计直接停止这份旁路观察，不影响原响应转发。

内存不仅是窗口：底层输出缓冲最坏约窗口+2×128 KiB+copy slack，另有最多 128 KiB 输入缓冲与 DCtx，见 `zstd_decompress.c:1970`、`:1993`、`:2237`。按每层约 17 MiB 留预算合理，仍不是 RSS 的硬限额。

**实测：** 三种分块支持长正文；多 frame／skippable frame 成功；截断／尾垃圾不能完整；第一 frame 或后续 frame 声明 32 MiB 窗口时拒绝，先前 frame 产生的摘要仍可保留并标 partial。

### 有界编码链与所有权建议

以下为结构建议，未写产品实现：

```text
UsageCapture
  └─ 最外层编码的 Stage
       ├─ gzip: MultiGzDecoder<Box<Stage>>
       ├─ deflate / br / zstd: 持久状态 + Box<Stage> + 固定输出块
       └─ terminal: Option<既有观察／解析状态>
```

1. 完整解析／校验编码声明后逆序建链，最多 4 个非 identity 层；identity 为 no-op。可沿用请求侧研究的 32 个列表片段预算，但请求模块和产品行为本轮不修改。未知、非法或超过支持预算只让该观察器 partial，原始 HTTP 字节照常走现有转发。
2. Stage 的 Write 实现消费一段输入，产生小块后直接调用下层 Stage；terminal 直接调用事件解析逻辑。W 不存 Vec／通道／网络输出。如此每层只保留 codec 工作区和少量 scratch，中间结果不会随一整个网络 chunk 或整条响应累计。递归深度由编码层数限制。
3. terminal 直接拥有解析状态；通过 gzip 的 get_mut 或其他层的 next 访问它。没有引用回 UsageCapture 的自引用，也不必使用 Arc／锁来让回调访问外部解析器；box 所有权自然延续跨 chunk 的状态。
4. 每次顶层 feed 后 gzip flush 输出到下层，各层 flush 向下传播；flush 不完成 SSE 事件，也不落库。外层解码器结束 flush 可能再产生最后输出，所以最终检查必须按**外层到内层**顺序。
5. gzip 用非消费式 try_finish，随后通过 get_mut 访问内层，保留错误时的 terminal 摘要。不要仅依赖 `finish(self) -> Result<W>`：它失败时不把 W 返回，直接消费整个链会丢失已知摘要。
6. 最后从 terminal 的 Option 中 take 出观察状态／摘要，之后其 Write 为无观察效果的消费；再销毁 codec。这样 codec 内部 Drop 的隐式 flush 不会在已结束／已写库后再次修改摘要。现有 UsageCapture::finish 与 observation 各自继续产生一次终态，不由 codec Drop 写库。

gzip／deflate 的 miniz 工作区同样不随正文增长：`REG/flate2-1.1.9/src/ffi/miniz_oxide.rs:37` 持有固定 InflateState；该状态的字典为 32768 字节数组，见 `REG/miniz_oxide-0.8.9/src/inflate/stream.rs:61`、`:70`。gzip 再叠加内部 32 KiB 输出和最多三项各 65535 字节逻辑头字段；没有每条响应增长的成员列表。

建议资源式：

```text
两份独立观察器 ≈ 2 × (各编码层的工作区之和 + P + 4 × 8 KiB)
P = 一份 SSE／JSON 解析器的明确缓冲预算
极端 8 个 br 层 ≈ 160 MiB codec 工作区 + 2P + 容器／分配器开销
```

如果 P 最多 2 MiB（例如大行和事件各有自己的 1 MiB 上限），总观察工作区估算约 164 MiB 加少量开销。P 的确切复用方式由主会话 SSE 设计决定。gzip 额外的内部 32 KiB 已计入对应 codec 估算，不应把每层结果再收进 P。标准长流不设累计总解压字节上限；完整 JSON、大行／大事件、未知编码、过多编码层和超窗口仍保留明确边界。

### EOF、body error 与 Drop 的 codec 合同

| 结束原因 | codec 行为 | 摘要行为 |
| --- | --- | --- |
| 正常 HTTP EOF | 外到内排出已缓冲输出；gzip try_finish；deflate StreamEnd；br ResultSuccess；zstd 位于完整 frame 边界；所有层无尾随输入 | 仅当传输、codec 和事件／JSON 都完整时允许 complete。 |
| body error | 只处理已收到的字节、最多排出现有工作区；执行同样结束检查或保守判未完成；不再读取网络 | 保留此前完整事件中已观察的 usage，强制 partial；即使已有 message_stop，也不能把传输错误判为完整。 |
| 下游取消／Drop | 同步结束检查，工作仅针对现存 decoder 状态；通过既有 Option::take 保护只完成一次；不等待网络、线程或数据库 | 保留已知 token／model，强制 partial；不能因解析器没有新输出就覆盖成完整零用量。 |
| 任一层解码错误／资源边界超出 | 对该观察链设置 sticky failed，后续 feed 无观察效果；停止使用错误后的 codec，原始转发继续 | 使用既有 decode_error／sampling_limit 分类，保留已有摘要，绝不恢复 complete。 |

这些检查只负责压缩完整性；gzip member／zstd frame 边界不是 SSE 事件边界，message_stop／[DONE] 也不能跳过后续 footer 校验。不要在每个 member、frame 或 flush 调用 parser 的最终完成方法。

### 最小探针、实测范围与复现

探针源：`research/incremental-codecs-probe.rs`。编译使用 rustc 1.96.0，直接链接现有 debug rlib，不运行 Cargo、不修改 target、不新增依赖；临时二进制／结果位于 `/tmp/cc2api-r4-incremental-codecs-onc6lci9/`。本轮 39 行观测的预期断言全部通过；5 种格式的普通样本各按 1／7／1024 分块，正文为 2,162,688 个合成字节，出口只记录长度与最大写入片段。

| 核心观测 | 结果 |
| --- | --- |
| gzip／zlib／raw／br／zstd 长输出 | 各分块方式均输出 2,162,688 字节；1／7 字节分块均在 EOF 前开始输出。 |
| gzip 多成员 | 4,325,376 字节，严格成功。 |
| gzip CRC／第二成员 CRC／截断 footer／截断 payload／尾垃圾／零尾巴 | 错误；允许保留错误前输出，不能 complete。 |
| zlib／raw 截断、尾随；zlib Adler 损坏 | 截断／trailing／错误，均非完整。 |
| br 截断／尾随／第二条流 | 非完整；不接受拼接 br。 |
| zstd 多 frame／skippable | 完整成功。 |
| zstd 截断／尾随；首帧／第二帧超 24-bit 窗口 | 非完整；后续超窗之前的输出保留。 |
| raw／zlib 头碰撞 | raw 成功 156 字节，zlib 失败，已证明嗅探边界。 |

复现（从仓库根目录执行；产物仍在系统临时目录）：

```bash
rustc --edition=2024 \
  .trellis/tasks/10-29-cc2api-sse-usage-observation/research/incremental-codecs-probe.rs \
  -L dependency=cc2api/target/debug/deps \
  --extern flate2=cc2api/target/debug/deps/libflate2-c79e56a90060f9a0.rlib \
  --extern brotli=cc2api/target/debug/deps/libbrotli-56d4ba4c62e4ba76.rlib \
  --extern zstd=cc2api/target/debug/deps/libzstd-6190ae9f85ef2992.rlib \
  -o /tmp/cc2api-r4-incremental-codecs-probe
/tmp/cc2api-r4-incremental-codecs-probe
```

产物 hash 改变后只需改为当前同版本 rlib 路径。br／zstd 的 1024 分块样本压缩体本身短于 1024，所以在该项唯一输入块之后才观察到输出；这不是“等待 HTTP EOF 才解码”，也不能声称所有格式／任意压缩块都能在最后一个压缩字节到来之前输出。

### 相关规范

- `.trellis/workflow.md` Phase 1.2：研究必须落盘；本次只研究，不修改 PRD／design／implement。
- `.trellis/spec/cc2api/backend/index.md`：先核对现有类型、接口与相关指南。
- `.trellis/spec/cc2api/backend/service-architecture.md:27`：Gateway 热路径、响应 chunk 与既有转发合同；请求整包编解码独立，不将其 worker／整包上限直接搬到本任务。
- `.trellis/spec/cc2api/backend/testing-quality.md:23`、`:42`：合成最小样本、敏感正文边界、压缩解码必须有资源上限。产品实施后仍需主会话完成格式／全量与 Gateway 集成检查。
- `.trellis/spec/cc2api/protocol/index.md`：本研究不修改身份、CCH、画像或协议载荷。

## Caveats / Not Found

- 没有阻塞选型的依赖 API 未知。真正需要评审确认的是有限 deflate 分流的兼容边界、最多 4 层及窗口预算；它们不是对“所有合法编码链”的无条件承诺。
- 探针验证消费／输出长度、结束状态和早期输出，未逐字节比较 SSE 摘要、未跑真实 Gateway、未测原始压缩体 >1 MiB、未做进程 RSS／CPU 峰值实验；这些属于主会话后续集成验证，不能用本探针代替。
- 本轮没有实现递归 Stage 或有限早期 deflate 回退器；它们是根据真实接口给出的所有权／状态建议。复杂编码链的产品验收仍需覆盖实际构建和结束顺序。
- 标准 br、24-bit zstd 窗口和 4 层资源策略会排除一部分原有宽松 helper 能读的输入。观察失败只影响摘要完整性，不能把响应改成错误或剥除 Content-Encoding。
- 固定块与窗口限制内存；它们不构成同步 CPU 时间硬上限。单个压缩输入块可能产生很多小块，空 member／skippable frame 也消耗 CPU；不要声称外包 async timeout 能抢占同步解码。若另加工作预算，耗尽只能停该旁路并 partial，而且必须明确其额外兼容范围。
- raw DEFLATE／br 没有通用内容 checksum，zstd checksum 可选；严格结束无法检出所有仍然构成另一条合法流的修改。
