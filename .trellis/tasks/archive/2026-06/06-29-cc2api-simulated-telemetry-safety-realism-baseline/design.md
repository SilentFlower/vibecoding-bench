# 技术设计

## 总体方向

本任务只处理 `cc2api` 内部生成的模拟 telemetry，不以真实 `/api/event_logging/v2/batch` 出站抓包作为运行时输入。改动集中在 `TelemetryService` 的 batch 构造、发送前扫描、诊断日志，以及 `GatewayService` 提供给 telemetry 的安全摘要。

## 边界

- `service/telemetry.rs`：负责事件字段模板、batch 构造、最终 payload 扫描、发送日志和 correlation fallback。
- `service/gateway.rs`：只提供安全摘要，例如文本长度、附件类型计数、tool block 长度、响应 usage；禁止传递 prompt、tool input 原文或响应正文。
- `model/identity.rs`：如需稳定 run/session 兜底，只复用已有 `RunProfile` / `DeviceProfile`，不新增账号敏感字段。
- 不改真实请求 body、CCH、`cc_version` 或 settings 页面。

## 假值字段处理策略

字段分三类：

1. 可安全推导：保留并使用真实摘要，例如 input text 字符长度、message 数、usage tokens、ttft、duration、cache marker count。
2. 暂不可推导但固定 0 明显虚假：省略字段，例如 `costUSD`、真实图片像素、部分 hook duration、内存 delta。
3. 需要保留但只能模拟：只在有合理分布或明确默认值依据时保留，并在测试中解释原因。

优先原则：宁可缺字段，也不要发送明显不可能或高度一致的假分布。

## 安全扫描

新增发送前扫描函数，输入最终 `serde_json::Value` batch，输出：

- 清理后的 batch。
- 扫描摘要：事件数、drop 字段数、drop 事件数、命中原因计数。
- 结构化日志字段：事件名、字段路径、原因、动作，但不包含原值。

扫描规则：

- key denylist：`authorization`、`cookie`、`token`、`api_key`、`prompt`、`tool_input`、`response_body`、`email` 等大小写变体。
- value pattern：邮箱、Bearer token、过长文本、疑似完整账号 UUID；完整 UUID 规则要避免误伤 `event_id` / `requestId` 这类 telemetry 自生成 ID，可按字段路径允许列表处理。
- 对 `additional_metadata` 先 base64 decode 为 JSON 扫描，再重新 encode 清理后的 metadata。
- 扫描异常时保守处理：丢弃对应 metadata 字段；batch 结构损坏时丢弃对应事件并记录原因。

## 诊断日志与 dry-run shape summary

正常发送路径记录：

- `event_count`
- `event_name_counts`
- `scan_dropped_fields`
- `scan_dropped_events`
- `scan_reason_counts`
- `status_code` 或 `error_kind`

可选 shape summary 作为测试/诊断 helper，不默认打印完整 JSON：

- 事件名分布。
- 每个事件的 `additional_metadata` key、类型和出现次数。
- 被扫描丢弃的字段路径和原因。

## correlation fallback

当前 `event_data.session_id` 已通过 `run_profile.session_id` 兜底，但 `TelemetryCorrelationStore` 的 key 来自 `MessageTelemetryContext.session_id`，缺失时会使用随机 `request_key`。本任务改为让 telemetry 记录请求时传入稳定 fallback session key：

- 优先使用 `context.session_id`。
- 缺失时使用当前 telemetry session 的 `run_profile.session_id`。
- 确保同一账号同一 auto telemetry session 内缺失 request session id 的请求仍共享 query chain。

## 兼容和回滚

- 账号级 `auto_telemetry=false` 仍是总开关。
- 安全扫描只会减少字段或事件，不应扩大敏感面。
- 如果日志量过大，可后续按 debug 级别或采样率收敛；本任务先保证可观测性。
