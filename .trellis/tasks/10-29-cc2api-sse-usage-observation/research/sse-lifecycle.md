# Research: SSE 事件边界与响应观察生命周期

- Query: R4-01／02 的统计解析器应如何接入实际响应生命周期，避免改动转发与重复计数？
- Scope: mixed；当前代码、既有冻结研究及官方 SSE／Messages 流协议。
- Date: 2026-10-29

## Findings

### 当前行为与入口

| 位置 | 已核实行为 |
| --- | --- |
| `cc2api/src/service/usage.rs:21` | `UsageCapture` 同时持有临时解析状态和数值摘要；`observer` 构造无 UsageStore 的独立诊断观察器。 |
| `usage.rs:112`、`:168` | 当前仅按 LF 分行，每条 `data:` 独立解析 JSON；因此多 data 事件和 CR-only 不能正确观察。 |
| `usage.rs:315` | 完成时还解析未结束行；这会把没有空行派发的残缺 SSE 数据提前当成有效事件。 |
| `usage.rs:343`、`:357` | `observation(self, complete)` 同步返回安全摘要；`finish(self, complete)` 异步提交用量，不等待数据库。 |
| `usage.rs:375`、`:388` | 压缩副本先整体积累，再逆序逐层解码；原字节和每层解码输出均限整个响应 1 MiB。 |
| `cc2api/src/service/diagnostics.rs:220`、`:307`、`:321`、`:365` | 每个 AttemptTrace 有自己的 UsageCapture；头到达记录既有 ttft_ms，压缩原字节积累 1 MiB，finish 后才解码。同步摘要影响尝试与根请求终态。 |
| `diagnostics.rs:450`、`:541`、`:578` | AttemptTrace／DiagnosticBody 的 Option::take 保证 EOF、末帧、body error、Drop 不重复收口；取消必须保留受控终态。 |
| `cc2api/src/service/gateway.rs:2552`、`:2565`、`:2623` | 正式成功 messages 建立用量观察器；非流探针实际调用走已有缓冲入口；普通响应走 SlotGuardBody。缓存命中等本地分支不增加正式用量。 |
| `gateway.rs:2819`、`:2866` | 每次实际上游发送创建独立诊断尝试，响应头后配置响应编码；429 等既有缓冲分支也要使用同一观察机制。 |
| `gateway.rs:7108`、`:7172`、`:7233`、`:7576` | 用量在 EOF／末帧／body error／Drop 一次完成；明文逐块解析，压缩从已有 stateful side tap 在结束后解码。 |
| `gateway.rs:7335`、`:7348` | stateful 压缩副本另有 16 MiB 上限和缓存锚点用途；本任务应解除正式用量对它的依赖，保留该用途和算法。 |
| `gateway.rs:3947` | 现有响应编码列表遍历重复 Content-Encoding、逗号分隔，规范为小写并忽略 identity；本任务沿用该解析边界。 |

### 事件规则与保守完整性

依据 [WHATWG SSE 解析规则](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream)（2026-10-29 读取，正文第 416–481 行）：

- 支持 LF、CRLF、CR；CR 与紧接 LF 可能分在不同网络 chunk，不能多产生一个空行。
- 流首一个 UTF-8 BOM 被忽略；跨 chunk 的前缀需要有限状态，不能把 BOM 字节当作字段内容。
- 注释以冒号开头；字段按首个冒号拆分，只去掉字段值开头至多一个 ASCII 空格；字段名大小写敏感。
- 同一事件的 data 字段以 LF 连接；遇到空行派发，JSON 解析放在整个 data 事件上。没有 data 的空块和注释不产生用量。
- EOF 不派发没有最终空行的事件。当前预先消费残行的逻辑需要移除；未派发的 data 不贡献 token，并保留 partial。
- 浏览器重连、id／retry 和事件回调不是本地统计观察器的职责；客户端得到的还是原始 SSE。

依据 [Claude Messages streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)（同日读取，第 123–150 行）：最终 message_stop 是结束证据；message_delta 的 usage 为累计值；未知未来事件须容忍。因此继续复用现有 `observe_value`／`merge_message_usage`，不求和重复 usage，也不要求收集完整文本、thinking 或工具参数。

### 资源与失败策略

- 保留 1 MiB 完整 JSON 上限，并对 SSE 每行及合并后的单个 data 事件分别设 1 MiB 上限；事件数和整条 SSE 长度不成为整包缓存。
- 大行或事件越界后丢弃该事件至下一个空行，以有界状态重新同步；不要只丢一条 data 行后错误地接受同一事件的残余 JSON。已有摘要保留，partial 与既有 sampling_limit 表示观察缺口。
- malformed data JSON 使用现有 invalid_payload；codec 格式错误／截断使用 decode_error；不要新增未经诊断 outcome 白名单同步的任意错误类型。
- 解码失败、取消、body error 后保留已完整观察到的 token，下游继续得到原帧／原错误。未知 token 在诊断中保持 null；用量表的默认零不成为“完整免费”的证据。
- 计价仍允许对已知用量折算部分费用，未知模型／未见用量仍未定价；本任务不改累计最大值、缓存明细及价格目录。
- 两套观察器复用同一实现，但不合并其持有者、落库和终态生命周期；避免为减少一次解码而引入跨重试的共享可变摘要。
- 同步解码必须每次只交付固定小输出块，不积累整条解压后响应；不能把正常长流失败简单改成更大的总长度限制。codec 工作区和逐次解码工作量仍需明确限制，见独立增量 codec 研究。

### 可复用验证入口

- `usage.rs:431` 起：跨块累计 max、响应模型／speed、压缩上限、缺失／损坏／未知模型。
- `diagnostics.rs:670` 起：原始字节与安全摘要；`:831` 起：decode_error／sampling_limit／invalid_payload、health 计数；取消和读取错误现有样例可扩展压缩输入。
- `gateway.rs:11670`：真实本地上游、Gateway、SQLite 用量与 DiagnosticsStore，一次性计数、JSON／SSE／压缩／取消、关闭自动遥测及缓存命中。应扩充同层测试，而非只测 helper。
- 追加长流对照：decoded >1 MiB 的可压缩 SSE，以及 compressed raw >1 MiB 的合成噪声 SSE；每个事件保持正常长度，客户端正文逐字节等于上游，头仍匹配；头尾用量及诊断不能丢。
- 资源负例：超大 JSON／行／事件、未知编码、压缩损坏／截断、缺 message_stop／缺空行；网络取消与 codec EOF 分别验证，不用真实账号推理。

### 相关规范

- `.trellis/spec/cc2api/backend/settings-database.md:122`：独立用量、一次收口、max 与缓存明细、部分费用和未知语义。
- 同文件 `:181`：诊断根／尝试、响应头 ttft_ms、安全摘要、采样上限、异步写入、observation_failures。
- `.trellis/spec/cc2api/backend/testing-quality.md`：Rust fmt／全量测试、热路径、采样和敏感信息边界。
- `.trellis/spec/cc2api/protocol/index.md`：身份与 CCH 现有回归，本任务不改请求封口。

## Caveats / Not Found

- 以上入口与现象均由当前代码／冻结研究定位，尚未实现或重跑产品测试；不能称为修复完成。
- 具体 codec 增量 API 与有界工作区由同任务 `incremental-codecs.md` 收敛；不存在取消整个响应上限就自动有界的保证。
- 同步逐块解码会增加逐帧 CPU；不把“无需完整缓冲／等待数据库”写成严格零延迟或生产 CPU 时限保证。
- 观察改进不保证所有畸形内容可恢复；资源越界允许保守停止对应观察并标 partial，但不能影响网络转发或主动补 message_stop。
