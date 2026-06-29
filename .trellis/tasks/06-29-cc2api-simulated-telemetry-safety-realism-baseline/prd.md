# cc2api 模拟遥测安全与真实性基线

## Goal

提升 `cc2api` auto telemetry 的模拟遥测安全性与可持续调试能力：清理明显假的固定占位字段，增加最终 payload 安全扫描和结构化诊断日志，并修正 correlation fallback 的稳定会话键，降低模拟痕迹和敏感字段泄露风险。

## 背景

- 当前 auto telemetry 不依赖真实 Claude Code 发出的 `/api/event_logging/v2/batch`，而是在 `cc2api` 内部构造模拟遥测 batch。
- 上一阶段已补齐 correlation ID、核心 API 事件、usage/ttft/stop_reason 摘要和脱敏 catalog。
- 当前仍存在一批明显模拟痕迹：`buildAgeMins=0`、`costUSD=0.0`、tool/attachment duration 或 bytes 为 0、image/document 统计粗糙或固定 0。
- 后续持续对齐需要可观测性：记录每批模拟遥测的发送成功/失败、事件分布、安全扫描结果、被丢弃字段/事件数量，而不是依赖真实 endpoint 抓包。
- `event_data.session_id` 已有 `run_profile.session_id` 兜底，但 `queryChainId` correlation 在 `MessageTelemetryContext.session_id` 缺失时会退到随机 request key，可能导致同一会话内 query chain 不连续。

## 需求

- 清理或降级明显假的固定占位字段：无法可靠推导时不要发送固定 `0` / `0.0`，优先省略字段；可安全推导时使用真实长度、数量或耗时摘要。
- 增加最终模拟 telemetry batch payload 安全扫描：在发送前检查敏感字段和值形态，禁止 prompt、tool input、响应正文、Authorization、Cookie、邮箱、完整账号 UUID、长文本进入 payload。
- 安全扫描命中时不得记录原值；日志只记录事件名、字段名、原因和处理动作。
- 增加结构化诊断日志：每批模拟 telemetry 发送前/发送后记录 batch 大小、事件名分布、扫描结果、drop 字段数、drop 事件数、发送成功/失败状态码或错误类型。
- 增加可选 shape summary / dry-run 诊断能力，用于后续和 2.1.195 脱敏 catalog 对比；该能力不能输出敏感值。
- 修正 correlation fallback：当请求 body 没有可提取 session id 时，`queryChainId` 的 session key 应使用稳定的 run/session 兜底，而不是随机 request key。
- 保持账号级 `auto_telemetry` 开关作为总回滚入口。

## 非目标

- 不接入或抓取真实 Claude Code 的 `/api/event_logging/v2/batch` 出站包。
- 不提交原始 telemetry body、token、Cookie、邮箱、完整账号 UUID、prompt、tool input 或响应正文。
- 不一次性复刻所有 Claude Code UI / hook / IDE / plugin 本地状态。
- 不修改 `/v1/messages` 主请求 body 顺序、CCH 或 `cc_version`。
- 不新增前端 Settings 开关，除非实现时证明仅靠日志无法控制风险。

## 验收标准

- [ ] 模拟 telemetry 不再发送当前已知的明显假固定值字段，除非字段可以安全真实推导并有测试覆盖。
- [ ] 最终 batch 发送前有安全扫描，能拦截敏感 key、敏感值模式和异常长文本，并有单测覆盖。
- [ ] 安全扫描日志不包含原始敏感值，只包含事件名、字段名、原因和处理动作。
- [ ] 每批模拟 telemetry 有结构化日志记录发送成功/失败、状态码或错误类型、事件数量、事件名分布和扫描摘要。
- [ ] 诊断 shape summary / dry-run 输出只包含事件名、字段名、类型、计数、drop 摘要，不包含真实值。
- [ ] 缺少请求 session id 时，correlation fallback 使用稳定 run/session key，同一 auto telemetry session 内 query chain 连续。
- [ ] 保持 prompt、tool input、响应正文、Authorization、Cookie、邮箱、完整账号 UUID 不进入最终 payload 或日志。
- [ ] `cd cc2api && cargo fmt --check`、`cd cc2api && cargo test telemetry --lib`、相关 gateway telemetry 测试通过。
