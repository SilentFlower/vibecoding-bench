# Brief — cc2api Claude Code base URL 风险控制

## Goal

- 为 `cc2api` 增加 Claude Code 非官方 base URL 隐藏上下文标记的低风险治理能力：默认只观测和清洗 telemetry，可显式启用 `currentDate` 规范化。

## Scope

- 新增 `claude_code_context_sanitizer_mode=off|report_only|normalize`，默认 `report_only`。
- 在 Claude Code `/v1/messages` 改写链路扫描 currentDate 标记，`report_only` 只输出脱敏日志，`normalize` 才修改命中日期句式。
- 扩展 telemetry sanitizer，删除 base URL / gateway / proxy 相关 key/value 痕迹。
- 同步 settings 默认值、DB 默认插入、管理 API 校验、Gateway 热缓存、Vue 设置页和测试。

## Non-Goals

- 不 patch Claude Code binary。
- 不试图阻止本地 CLI 读取 `ANTHROPIC_BASE_URL`。
- 不修改 Claude Code 版本画像、CCH seed、beta 顺序、bootstrap 或账号迁移策略。
- 不默认启用 normalize，不记录完整 prompt/system/request body。

## Key Context

- 客户端检测发生在请求进入 `cc2api` 之前；`cc2api` 只能在网关阶段扫描、记录、可选规范化和 telemetry 清洗。
- 请求体改写位置在 `cc2api/src/service/rewriter.rs`，必须发生在最终 CCH / `cc_version` 刷新之前。
- settings 链路涉及 `settings_store.rs`、`db.rs`、`handler/router.rs`、`service/gateway.rs`、`web/src/components/Settings.vue`。
- telemetry 清洗入口在 `cc2api/src/service/telemetry.rs::sanitize_telemetry_payload` 及其 `sensitive_field_reason` / `sensitive_key`。
- 日志必须只输出路径、hash、长度、模式、动作等脱敏摘要。

## Acceptance

- 默认 `/admin/settings` 返回 `claude_code_context_sanitizer_mode=report_only`。
- `report_only` 命中 currentDate 标记时不改 body，只记录脱敏 warning。
- `normalize` 命中时规范化日期句式，且发生在 CCH / `cc_version` 刷新前。
- telemetry sanitizer 删除 base URL / gateway / proxy 痕迹，不误删正常 Anthropic 官方 host 字段。
- 管理页可切换并保存 `off|report_only|normalize`，保存后热路径立即生效。
- `cd cc2api && cargo fmt --check && cargo test` 通过；涉及前端时 `cd cc2api/web && npm run build` 通过。

## Next Step

- 用户确认 planning artifacts 和 brief 后，运行 `python3 ./.trellis/scripts/task.py start .trellis/tasks/07-01-cc2api-claude-code-base-url-risk-controls`，随后进入 Phase 2.1 的 `trellis-route(implement)`。
