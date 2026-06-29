# 技术设计草案

## 总体方向

`TelemetryService` 需要从“固定少量事件字段”演进为“按事件类型生成安全 metadata 模板”。该任务应分阶段落地，每一阶段都要有脱敏抓包对比，而不是一次性硬编码大量字段。

## 字段来源分级

- 请求体可推导：model、betas、messagesLength、tool_count、attachment_count、thinkingType、stream、system prompt block count。
- 响应可推导：durationMs、ttftMs、status、stop_reason、usage token/cache 统计。
- 网关运行时可推导：attempt、requestId、previousRequestId、queryChainId、messageID、session_id。
- 客户端本地不可得：UI renderer 内部状态、真实 permission mode 的完整上下文、hook 执行详情、IDE 状态。
- 禁止发送：prompt、tool input、响应正文、token、Cookie、邮箱、完整账号 UUID。

## 架构边界

- `service/telemetry.rs` 保持 telemetry 构造入口。
- 请求/响应摘要继续由 `GatewayService` 提供，禁止把完整 body 传进 telemetry queue。
- 新增 correlation state 必须按账号/session 隔离，不能跨账号复用 ID 链。
- 事件 metadata 模板应按事件名拆分，避免所有事件输出同质字段。

## 验证

- 单测验证字段存在性、敏感字段缺失、ID 稳定性。
- 脱敏抓包 diff 验证事件名分布、metadata key 分布、env key 分布。
- 远程灰度验证 event_logging 出站 header 和 body shape。

## 回滚

- 保留 `auto_telemetry` 账号级开关。
- 新增阶段性设置时默认可以关闭具体增强，避免一次性扩大上游事件面。
