# 压缩请求的解码与重编码设计

## 数据流与所有权

原始 HeaderMap → token／UA 准入 → 解析并冻结编码链 → 有界读取和严格解码 → 既有逻辑正文策略／调度／改写／CCH／缓存 → 每次发送前按原链重编码 → 已有 runtime transport。

新增请求专用模块 `cc2api/src/service/request_body_codec.rs`，由 `service/mod.rs` 注册，Gateway 两个入口共用。不移动 Rewriter 业务逻辑，不改响应 helper。模块只处理字节及编码链，不处理账号、JSON、画像、数据库或 HTTP 发送；Gateway 将明确的编解码错误映射到现有 Anthropic error response。

实施分工为独立 codec 模块和 Gateway 接线两部分，冻结以下内部接口；不改变已批准行为范围：

```rust
pub(crate) const REQUEST_BODY_LIMIT: usize = 10 * 1024 * 1024;
// RequestBodyEncoding 实现 Clone、Default（默认无编码）。
pub(crate) enum RequestBodyCodecError {
    InvalidEncoding,
    UnsupportedEncoding,
    TooLarge,
    InvalidBody,
    Internal,
}
// 以下为 RequestBodyEncoding 的关联函数和方法签名。
pub(crate) fn from_headers(headers: &HeaderMap) -> Result<Self, RequestBodyCodecError>;
pub(crate) fn is_encoded(&self) -> bool;
pub(crate) fn content_encoding(&self) -> Option<String>;
pub(crate) async fn decode(&self, body: Bytes) -> Result<Bytes, RequestBodyCodecError>;
pub(crate) async fn encode<'a>(&self, body: &'a [u8]) -> Result<Cow<'a, [u8]>, RequestBodyCodecError>;
```

这里 HeaderMap 来自 Axum HTTP 类型，Bytes 沿用已有 bytes 依赖，Cow 为标准库类型。Gateway 负责 HTTP 错误映射、读体错误细分和出站传输头清理；codec 的无编码 encode 返回 Borrowed，避免原路径额外复制。代码中的实际定义仍须含中文用途／参数／返回文档。

## 原始头与入口

1. 保留 router token 鉴权、count_tokens POST 和 Gateway UA 策略的现有优先级。在消费 Request 前保存原始 Content-Encoding 全部值；不依赖 `extract_headers` 的有损 HashMap。
2. `get_all` 按值顺序读取，每值按逗号拆分，仅去掉 SP／HTAB；完整 token 按 ASCII 大小写无关匹配。忽略空项／identity；总片段最多 32，实际压缩层最多 4。先验证整条链再解码，保留 x-gzip 别名，有效出站值统一小写并保持顺序。
3. 无有效编码时保留原有读取／正文处理路径，不嗅探 magic，不按 Accept-Encoding 或版本压缩。identity／空声明不产生出站 Content-Encoding。
4. 压缩请求原字节最多 10 MiB，逆序解码，每层输出最多 10 MiB。大小错误与普通读取 I/O 错误分开；无编码原路径状态码不变。实际编解码使用 `spawn_blocking`，无编码不增加该调度；不宣称 async timeout 能中断已执行的同步 codec。
5. 解码后变量表达逻辑正文。通用 Gateway 保留原非 JSON 回退；count_tokens 保留严格 JSON object／model 校验。所有输入编解码拒绝先于正文策略及账号相关副作用返回。

## 严格解码与限制

当前 lockfile API 的验证证据见 `research/findings.md`：

| 编码 | 实现与成功条件 |
| --- | --- |
| gzip／x-gzip | `flate2::bufread::MultiGzDecoder`；完整结束并检查 CRC／ISIZE，接受全部 member，不能只取第一段。 |
| deflate | `flate2::Decompress` 分块处理，必须 StreamEnd 且耗尽输入；先 zlib，格式失败才尝试严格 raw，超限不回退。 |
| br | `BrotliState::new_strict` ＋ `BrotliDecompressStream`，成功且耗尽输入；仅标准窗口，不接 large-window 扩展。 |
| zstd | `stream::read::Decoder::with_buffer`，首次读取前 `window_log_max(24)`，完整 EOF；支持连续和 skippable frame，不启用 single_frame。 |

输出用剩余额度加 1 判断超限，恰好 10 MiB 仍读取结尾校验。不得用响应 helper、宽松 reader EOF 或“只读 limit 字节”证明完整性。

| 错误 | 本地响应 |
| --- | --- |
| 非法声明／总片段超过 32；损坏、截断、尾随内容、无法在支持窗口内解码 | 400，描述无效声明或解码支持边界 |
| 未知合法编码／有效编码层超过 4 | 415 |
| 压缩原字节或任一层输出超过 10 MiB | 413 |
| worker／本地编码异常 | 500；本次业务请求不提交 |

错误为可解析 Anthropic error object，不回显原始 header／正文、凭据或库内部细节；不用不稳定库错误字符串假装精确分类窗口错误。普通无编码读体错误保持原状。

这些是有限支持范围：4 层、10 MiB 中间层和 16 MiB 窗口会排除部分格式合法的输入；不宣传支持任意编码链、总内存硬限额或可取消 CPU 期限。输入／输出上限不是全请求内存上限；空 member／frame 仍有 CPU 成本，本项不引入全局调度框架。

## 逻辑正文与出站编码

- 解码后的原始逻辑字节及 body_map 保留既有准入、真实 Session、sticky、RPM、分类器和缓存含义；根键过滤、身份、池映射、普通 Session 有限对齐及 CCH 顺序保持现状。
- 不把 `final_body` 提前替换为压缩数据。`forward_request` 的诊断、日志、响应类型判断和 signature repair 继续消费逻辑正文。冻结编码计划传入普通发送、count_tokens 发送及 signature 重试；只在网络调用前生成本次 wire bytes。
- 编码正序执行：gzip／x-gzip 使用 GzEncoder；deflate 出站使用标准 ZlibEncoder（兼容 raw 入站不保留非标准包装）；br 使用可传播完成错误的 CompressorReader 或 BrotliCompress；zstd 使用标准 encoder。使用固定普通参数，例如 gzip 默认、br q=4／lgwin=22、zstd level=1，不猜原生容器参数。
- 不对编码结果新增沿用 10 MiB 的拒绝，避免逻辑正文因容器膨胀失效；encoder 完整成功后才采用结果，防止 finish 错误或部分输出发出。仅处理有界入站衍生的数据，不新增任意编码参数。
- 在出站头副本中去除 Content-Length／Transfer-Encoding／Content-Encoding 的全部大小写变体，有效链写入唯一 Content-Encoding。交给 `ordered_anthropic_headers` 及 `.body(Vec<u8>)` 生成真实长度，沿用 HTTP/1 大小写机制，不改画像头序常量。
- PreparedRequest、v3 bridge 和账号发送器不新增字段；Gateway 内保留逻辑正文，交给既有 transport 的 bytes 已是最终编码字节。直连与 v3 使用同一约定。

## 重试、缓存及副作用

- 首次发送、401、signature 两阶段和外层切号共用入站编码选择。signature 必须先完成本次逻辑正文／CCH 修复，再重编码；不复用初次压缩体，不在压缩字节上改 JSON。
- 本地拦截／缓存命中沿用原响应及零业务上游语义，不为编码增加网络请求。缓存键基于逻辑正文，容器参数不产生新缓存维度。
- 不新增遇到 400／415 就改明文的回退或重试；上游对 br／zstd 等编码的支持由其响应决定，loopback 成功不等于真实 Anthropic 推理验证。
- 入站拒绝无账号副作用；发送阶段内部失败仅保证本次业务请求未提交，已有 admission／Hello／自动遥测不承诺回滚或重排。

## 验证与回退

合成 Gateway＋loopback 检查实际发送头、原始字节、解码后的逻辑正文、CCH、重试及拒绝副作用；直连覆盖真正 `.body(Vec<u8>)` 长度。补 transport／sender 合同断言或复用既有 v3 原始字节验证，明确证据范围，不启动生产容器或真实推理。

产品变更限请求模块、注册及 Gateway 接线／相关测试。撤销该组 diff 可恢复产品基线，不撤销既有 R2／R3 修复。检查通过后按既有流程同步 Spec 和任务记录。
