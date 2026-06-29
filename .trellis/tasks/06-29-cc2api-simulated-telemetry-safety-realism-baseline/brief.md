# Brief — cc2api 模拟遥测安全与真实性基线

## Goal

- 提升 `cc2api` auto telemetry 的模拟遥测安全性与可持续调试能力：清理明显假的固定占位字段，增加最终 payload 安全扫描和结构化诊断日志，并修正 correlation fallback 的稳定会话键。

## Scope

- 清理或降级明显假的固定占位字段：无法可靠推导时不发送固定 `0` / `0.0`，可安全推导时使用真实长度、数量或耗时摘要。
- 增加最终模拟 telemetry batch payload 安全扫描，覆盖顶层 `event_data` 和 base64 `additional_metadata`。
- 安全扫描命中时清理字段或丢弃事件，并记录事件名、字段名、原因、动作，不记录原值。
- 增加每批模拟 telemetry 的结构化日志：事件数、事件名分布、扫描摘要、发送成功/失败状态码或错误类型。
- 增加可选 shape summary / dry-run 诊断 helper，用于后续和 2.1.195 脱敏 catalog 对比，输出只包含 shape 信息。
- 修正 correlation fallback：请求 body 缺少 session id 时，`queryChainId` 的 session key 使用当前 telemetry session 的 `run_profile.session_id`，而不是随机 request key。

## Non-Goals

- 不接入或抓取真实 Claude Code 的 `/api/event_logging/v2/batch` 出站包。
- 不提交原始 telemetry body、token、Cookie、邮箱、完整账号 UUID、prompt、tool input 或响应正文。
- 不一次性复刻所有 Claude Code UI / hook / IDE / plugin 本地状态。
- 不修改 `/v1/messages` 主请求 body 顺序、CCH 或 `cc_version`。
- 不新增前端 Settings 开关，除非实现时证明仅靠日志无法控制风险。

## Key Context

- 主要文件：`cc2api/src/service/telemetry.rs`、`cc2api/src/service/gateway.rs`、必要时 `cc2api/src/model/identity.rs`。
- 当前 `event_data.session_id` 已有 `run_profile.session_id` 兜底，但 correlation key 缺少 request session id 时会退到随机 `request_key`。
- 字段处理原则：宁可缺字段，也不要发送明显不可能或高度一致的假分布。
- 安全扫描必须扫描 base64 解码后的 `additional_metadata`，清理后再编码。
- 日志和 shape summary 都不能输出真实敏感值。
- `auto_telemetry=false` 仍是总回滚入口。

## Acceptance

- 模拟 telemetry 不再发送当前已知的明显假固定值字段，除非字段可以安全真实推导并有测试覆盖。
- 最终 batch 发送前有安全扫描，能拦截敏感 key、敏感值模式和异常长文本，并有单测覆盖。
- 安全扫描日志不包含原始敏感值，只包含事件名、字段名、原因和处理动作。
- 每批模拟 telemetry 有结构化日志记录发送成功/失败、状态码或错误类型、事件数量、事件名分布和扫描摘要。
- 诊断 shape summary / dry-run 输出只包含事件名、字段名、类型、计数、drop 摘要，不包含真实值。
- 缺少请求 session id 时，correlation fallback 使用稳定 run/session key，同一 auto telemetry session 内 query chain 连续。
- 保持 prompt、tool input、响应正文、Authorization、Cookie、邮箱、完整账号 UUID 不进入最终 payload 或日志。
- `cd cc2api && cargo fmt --check`、`cd cc2api && cargo test telemetry --lib`、相关 gateway telemetry 测试通过。

## Next Step

- 确认 planning artifacts 和本 brief 后，运行 `task.py start` 激活任务；实现前读取 cc2api backend/protocol spec，并从假值字段清理与 payload scanner 开始。
