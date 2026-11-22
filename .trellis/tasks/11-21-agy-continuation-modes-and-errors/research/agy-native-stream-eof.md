# AstrBot 空流的原生收尾排查

## 线上证据

- 北京时间 2026-11-21 18:29:58.929，`c7521e93` 的原生尝试 `214a3d06` 读取到用量，输入 254,077、缓存 251,337。源帧缺少输出与结束原因。18:29:58.997 记录 `model_end`。18:29:59.041 记录 `native_control.submission.native_stream_incomplete.unknown.RuntimeError.ineligible_error`。原生接收结束到 Flower2API 报错相隔约 44.6 毫秒。
- 同一窗口发送器容器持续运行，重启计数为 0。该请求记录的终态为 `error`，此前对应日志中没有取消或进程退出事件。保留的 `agy_native_tls` 快照是 `http_entity_from_tls_accepted_write`，覆盖请求出站，响应 HTTP 状态为空。公开记录中的 200 来自账号发送器响应，原生控制状态为 `unknown`。
- 同账号同模型 `gemini-4-hydrogen` 在 17:55 的 `f5f008b9` 已出现同类错误。用量为 145,461 输入。约两秒后启动的 `114af732` 为独立原生尝试，入口正文与转换后的 Gemini 正文哈希均一致，派生会话一致，这次成功。该样本早于 v1.29.2 切换。18:29 的两笔近邻样本中另有一笔 253,386 输入成功。
- 北京时间 17:44 至 18:43 拉取的同账号同模型样本共 10 次。CRIU 恢复进程执行的 9 次中，7 次成功、2 次存在该错误。普通启动 1 次成功。失败和成功都出现在恢复进程中，启动方式与失败的因果关联待验证。

## 真实原版隔离回环

固定 AGY 1.5.9 原版，实际网关、账号发送器、本地 TLS 代理及 Anthropic Messages 入口。隔离容器无外网，全部使用合成上游响应。保持同样的首个用量帧，改变后续 HTTP 响应的收尾方式。

| 本地上游行为 | 原生接收事件 | `SendUserCascadeMessage` 的实际结果 |
| --- | --- | --- |
| 用量后发送完整 HTTP 最后分块，缺少模型结束帧 | `model_end` | HTTP 200，模型源终态仍缺失 |
| 用量后在下一个 HTTP 数据块中途停止 | `model_end` | HTTP 500，`stream reading error: unexpected EOF` |
| 正常交付内容、STOP 和用量 | `model_end` | HTTP 200，正常完成 |

在隔离适配器中，把原生控制状态的交付延后 200 毫秒以复现竞态。原逻辑把两类异常都记录为 `native_control.submission.native_stream_incomplete.unknown`。等待控制状态后，前一类保留 `native_stream_incomplete` 和控制 200，后一类恢复 `native_request_failed` 和控制 500。两类异常在当前公开网关上都先返回 HTTP 200，SSE 只有 `message_start` 和 `error`。正常对照收到文本与 `message_stop`。

## 修复验收

- 将接收通道关闭、源模型终态和控制调用结果分别记录。保留真实状态码和脱敏错误类别。接收通道关闭以后，使用原请求剩余时间等待控制状态。
- 用同一批本地样本验证开流前保留明确 HTTP 错误和开流后保留 SSE 错误。流式首帧提交与控制状态采集各自验收。
- 18:29 这笔线上请求的原生控制结果和模型响应侧收尾细节缺失。它的具体触发原因仍待验证。源观察点记录的是 Go 接收通道关闭。两种物理收尾在该观察点上表现相同。[接收观察点](../../../../services/orchestrator/agy_runtime/source/observer.c#L365) · [控制结果与提前退出](../../../../services/orchestrator/agy_runtime/kernel.py#L548)
