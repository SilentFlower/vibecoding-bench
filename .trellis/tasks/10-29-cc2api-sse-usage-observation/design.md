# 设计：SSE 事件与压缩长流统计

## 依据与边界

- 需求来自 [prd.md](prd.md) 的 R1–R5；当前产品基线是 cc2api `7a5495127f379f66e16b79a48da168088d08002f`。
- 事件／生命周期证据见 [sse-lifecycle.md](research/sse-lifecycle.md)；具体增量 codec API 与探针结论见 [incremental-codecs.md](research/incremental-codecs.md)。
- 修改统计观察副本，客户端仍由已有 Body 包装转发原帧。观察器不发请求，不消费另一份网络流，不操作 Content-Encoding／Content-Length，也不补消息结束帧。
- 正式用量与独立诊断共用实现、各自持有状态与一次性终结责任。此轮不把两个持有者重构成跨重试共享对象。

## 数据流与模块职责

1. 观察器创建后、任何 body 数据到达前，以已有 `response_content_codings` 结果配置编码链。
2. 每个原始响应片段送入同步增量解码层；无编码直接进入正文观察器。编码层按 Content-Encoding 的逆序执行。
3. 每层输出小块立即进入下一层，末端直接进入 JSON／SSE 观察器，随后释放该块；不积累整条压缩正文或中间解码结果。
4. JSON 在既有上限内缓冲；SSE 按事件派发。完整事件复用现有用量合并与安全摘要规则。
5. 生命周期结束时，验证 codec 完整性并汇总摘要，再由现有 UsageStore 异步记录或 DiagnosticsStore 队列提交。观察错误不改变原帧、原传输错误及取消行为。

拟涉及的文件：

| 文件 | 责任 |
| --- | --- |
| `cc2api/src/service/usage.rs` | 有界事件状态、JSON 观察、累计摘要和统一编码观察入口；保留现有公共构造／结束职责。 |
| `cc2api/src/service/response_body_codec.rs`（新增） | 仅负责统计所需的同步增量解码、结束校验和资源边界；不复用整包请求 codec，不新增依赖。 |
| `cc2api/src/service/mod.rs` | 注册内部模块。 |
| `cc2api/src/service/diagnostics.rs` | 在 headers 配置观察器，observe 每块原始数据；移除本地压缩整包采样，保留根／尝试终态与错误计数。 |
| `cc2api/src/service/gateway.rs` | 正式用量逐块观察编码数据，解除对 stateful 压缩副本的依赖，缓冲分支复用同一入口；扩展实际转发回归。 |

不修改 UsageStore／DiagnosticsStore 的数据结构、SQL、价格目录、路由或管理 API。

## SSE 与 JSON 状态

- 保留响应内容的既有 JSON／SSE 自动识别方式，显式处理流首 BOM／前导空白与跨块前缀，前缀缓冲受同一大小限制；不按客户端 UA 猜测响应格式。
- SSE 使用跨块行状态：LF、CR、CRLF 都结束行，CR 后紧随的 LF 只消耗一次。流首一个 UTF-8 BOM 忽略。
- 注释忽略；字段按首个冒号划分，只去掉值首一个 ASCII 空格，字段名大小写敏感。data 字段按 LF 连接，空行才派发；event／id／retry 等字段不进入持久化。
- 每个完整 data 事件执行一次 JSON 解析。`[DONE]` 保留既有兼容；未知合法事件忽略非摘要字段。字段最大值、零值、缓存写总量和 TTL 明细继续复用既有合并逻辑。
- EOF 不解析未派发的 data；残缺 data 标记 partial，不能贡献未完整事件内的 token。纯注释和没有 data 的空块不制造用量。
- 完整 JSON 上限 1 MiB；SSE 单行上限 1 MiB，合并后单事件 data 上限 1 MiB。超过事件上限，清空临时内容并跳过至下个空行后再同步，保留 sampling_limit 与此前已知摘要。
- JSON 与 SSE 的正文缓冲按类型互斥；SSE 行与事件的原始字节缓冲合计至多 2 MiB。此值不包含 JSON 解析树和安全摘要字符串等临时分配，不能写成该观察器的总内存硬上限。
- SSE 总事件数、整条原始响应长度和累计解码长度不使用原来的 1 MiB 整包门槛；正常长度事件组成的长流不因累计大小丢失头尾用量。

## 增量解码与所有权

- 使用现有 flate2／brotli／zstd 依赖；实际方法与版本以 codec 研究中本地源码为准。gzip／x-gzip 使用 `MultiGzDecoder` 校验多 member 与 CRC／ISIZE；deflate 使用低层 `Decompress`；br 使用 strict 状态机；zstd 使用 raw Operation 与窗口限制。
- 解码图以持久的下游写入对象连接，终端直接是事件／JSON 观察器。gzip 的 Writer 不能是积累全部输出的 Vec；库内 32 KiB 暂存输出也必须立即写给下游。
- 其余低层 decoder 每轮使用 8 KiB 输出缓冲，跟踪真实 consumed／produced 和终结状态；无进度时按需要更多输入或受控错误结束，不允许无限空转。
- 配置必须先于首块输入；配置失败只禁用该次观察并记受控错误，不拒绝业务响应。已有一次性 `observe_encoded` 缓冲入口应委托同一配置／feed／finish 机制，不能再保留另一套整包解析结果。
- 终结时先检查外层并传递其已有剩余输出，再终结内层；不能在尚需输入时伪造正常 EOF。合法结束后再有不允许的尾字节须标 partial。
- 已解码并派发的用量属于可保留的部分观察；后续 footer 损坏、传输中断或取消不清空它，也不将观察标为完整。没有有效用量时仍未定价。

### deflate 兼容选择

- 常规 zlib 与 raw-deflate 均支持；为有界增量处理，先收集有限前缀，按有效 zlib 头选择 zlib，否则选择 raw。
- 这是格式分流，不是证明原始格式。合法 raw 流可以具有 zlib 头前缀；旧整包实现“zlib 失败后重放全部字节为 raw”无法在不保留整流的前提下无条件等价。
- 此轮不引入编码链上的多分支解析与回滚树。二义输入或选择后的晚期格式失败保守标记 partial／decode_error；原始响应仍照常返回。不根据错误触发新的上游重试，也不把失败的 zlib 候选宣布为完整 raw。
- 此边界必须体现在回归、Brief 和完成说明中；普通两种 deflate 以及预算内组合必须正常采集。

## 资源预算

| 对象 | 边界 |
| --- | --- |
| JSON／SSE 行／事件 data | 各 1 MiB，按类型使用，不保存整个 SSE。 |
| 实际编码层 | 最多 4 层，identity 不计；超出仅统计 sampling_limit。 |
| 每层输出暂存 | 低层接口 8 KiB；gzip 库内部最多 32 KiB，直接下推，不在 sink 累积。 |
| gzip 头／窗口 | 库的有限头字段与 DEFLATE 工作区；超长头不无限积累。 |
| Brotli | 标准窗口至多 24 bits，拒绝 large-window 扩展。 |
| zstd | 每层 WindowLogMax(24)，后续 frame 同样受 16 MiB 窗口限制。 |
| 格式终结 | 完整状态及输入耗尽；多 gzip member、多 zstd frame／skippable frame 按 codec 规则处理。 |

窗口上限不等于总内存：Brotli 还含有界表等状态；两套观察器均达到四层最大标准 Brotli 窗口时，codec 工作区约 160 MiB，另有解析状态和既有 stateful 副本。常见单层 gzip 不使用 Brotli 工作区。实施必须验证不随事件总数增长，不能声称全进程 RSS 限于 16 MiB。

本方案不新增线程、无界任务队列或数据库等待。同步逐块解码增加 CPU，输出分块和窗口限制不构成可取消的 CPU 时间保证；若测得普通流明显阻塞，须回到本设计解决，不通过移除全部上限掩盖。

## 生命周期与诊断合同

- SlotGuardBody 在每块数据后观察；EOF／确定末帧调用 finish(true)，body error／Drop 调用 finish(false)，仍由 Option::take 保证一条正式用量记录。
- AttemptTrace 在响应头配置同一解码机制，继续同步生成 MessageObservation，先更新 last_attempt 再交给根保护器终结；保留现有 complete／cancelled／body_error／transport_error 优先级。
- codec／语法／资源故障分别沿用 decode_error／invalid_payload／sampling_limit。每次故障尝试只计一次 observation_failures，不将这些错误判成 Anthropic 上游业务错误。
- 不改 `ttft_ms` 在响应头到达时记录的定义；不新加 first_token 指标。缺 message_stop 的有效事件摘要继续 partial，不自动补帧。
- 非流探针实际调用、429 等已有缓冲分支使用同一观察流程；本地 cache hit／mock／count_tokens 的计费边界不变。
- 不改 stateful side tap 16 MiB 上限、锚点完成逻辑及自动 message telemetry 的独立解析／载荷；新用量观察器不再依赖那份副本。

## 验证与回滚

- 验证矩阵及执行顺序见 [implement.md](implement.md)。以实际 Gateway＋本地上游＋临时 SQLite／DiagnosticsStore 作为外部行为证据，单独 codec 探针不是产品完成证明。
- 无迁移、无设置、无部署。回滚只需回退本次统计观察与接线代码；已记录历史摘要不重算。提交／推送按项目独立评审流程执行。
- 若真实实现揭示技术选择不能满足以上资源或行为合同，先更新本设计和实施清单，再按 Brief 增量规则处理；不扩大为响应保活或计时重构。
