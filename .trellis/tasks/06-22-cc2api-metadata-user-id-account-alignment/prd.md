# fix: cc2api metadata user_id account_uuid alignment

## Goal

修复 `cc2api` 在 Claude Code 客户端模式下改写 `/v1/messages` 的 `metadata.user_id` 时只替换 `device_id`、保留下游原始 `account_uuid` 的身份不一致问题。目标是在不改变 `session_id`、不影响粘性路由和 stateful cache key 的前提下，让上游请求体中的 `device_id` 与 `account_uuid` 都对应当前选中的上游账号。

## Background / Known Context

- 用户确认优先修复 cc2api 风险点 5：`metadata.user_id` 中 `account_uuid` 与当前上游账号不一致。
- 当前 `cc2api/src/service/rewriter.rs::rewrite_metadata_user_id` 在 JSON 格式下只写入 `device_id`，旧格式下只替换 `user_` 后的 device 前缀。
- `X-Claude-Code-Session-Id` 由改写后 body 的 `metadata.user_id.session_id` 提取；只改 `account_uuid` 不应改变 header。
- `AccountService::generate_session_hash` 与 `Rewriter::stateful_session_key` 都使用 `session_id`，不使用 `account_uuid`。
- 为避免影响 Anthropic prompt cache、cc2api 粘性路由和 stateful cache，本任务不改写 `session_id`。

## Requirements

- Claude Code 客户端模式下，JSON 格式 `metadata.user_id` 必须同时改写：
  - `device_id` 为当前上游账号的 `device_id`。
  - `account_uuid` 为当前上游账号派生/保存的 `account_uuid`。
  - `session_id` 保持下游原值不变。
- 旧格式 `user_{device}_account_{uuid}_session_{uuid}` 必须改写为当前上游账号的 `device_id` 与 `account_uuid`，并保留原 `session_id`。
- 不改变 API 模式现有行为；API 模式仍可覆盖下游 `metadata.user_id` 并生成自身稳定 session。
- 不引入新 setting，不改前端，不改 DB schema。
- 改写后 CCH 仍必须在最终 body 上计算。
- 日志和测试不得包含真实 token、邮箱、组织 ID、账号 UUID 映射或完整抓包。

## Acceptance Criteria

- [ ] JSON `metadata.user_id` 输入中 `account_uuid=A`，选中账号为 B 时，输出 `account_uuid=B`、`device_id=B`、`session_id` 保持原值。
- [ ] 旧格式 `metadata.user_id` 输入中账号 A 与 session S，选中账号为 B 时，输出使用账号 B 的 `device_id/account_uuid`，且 session S 保持原值。
- [ ] `rewrite_headers` 生成的 `X-Claude-Code-Session-Id` 仍等于保留后的 `session_id`。
- [ ] 现有 API 模式 metadata 注入测试继续通过。
- [ ] `cd cc2api && cargo fmt --check && cargo test` 通过。

## Out of Scope

- 不处理 telemetry / GrowthBook eval 字段形态差异。
- 不改写 `session_id` 派生策略。
- 不改带 `cache_control` 的 system block 清洗策略。
- 不调整账号调度、粘性会话、stateful cache 选点策略。

## Research References

- `.trellis/spec/cc2api/backend/service-architecture.md`
- `.trellis/spec/cc2api/backend/testing-quality.md`
- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`
