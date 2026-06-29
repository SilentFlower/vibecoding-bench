# Brief — cc2api 2.1.195 指纹升级与抓包分析

## Goal

- 将 `cc2api` 的 Claude Code 版本画像从 `2.1.187` 升级到真实抓包验证过的 `2.1.195`，重点对齐近期封号风险相关的 HTTP wire 指纹。

## Scope

- 基于远程抓包 `23594999fa77` 的脱敏摘要更新 `cc2api` 内置版本画像。
- 新增并默认启用 `2.1.195` profile，保留 `2.1.187` / `2.1.185` / `2.1.173` 作为回滚选项。
- 对齐 `version/version_base/build_time`、`allowed_claude_code_versions`、User-Agent、Stainless runtime、`cc_version`、CCH、beta、bootstrap、telemetry env、settings 和账号 canonical env 迁移。
- 更新前端 Settings 的 fallback profile 列表和默认值。
- 补充后端和必要前端验证。

## Non-Goals

- 不逆向或更改 TLS 指纹链路，除非实现中出现 HTTP 层全部对齐仍无法解释的明确证据。
- 不提交原始抓包、完整请求/响应正文、token、Cookie、邮箱、账号 UUID、完整 prompt。
- 不调整账号调度、限流策略或封号恢复策略。
- 不在本任务内执行生产部署；部署与远程 DB 验收作为后续确认动作。

## Key Context

- 原始抓包已拉到任务本地 `evidence/`，任务内 `.gitignore` 排除整个 `evidence/`；可提交证据仅为 `research/run-23594999fa77-summary.md`。
- 2.1.195 抓包确认：`X-Stainless-Runtime-Version=v26.3.0`，`env.build_time=2026-06-26T01:00:56Z`，`env.node_version=v26.3.0`。
- `cc_version` 后缀算法 30/30 命中现有规则；Haiku 流式标题为 `2.1.195.113`，Opus 主请求为 `2.1.195.aff`。
- CCH 30/30 命中 `2.1.172+` top-level 规范化规则和 seed `0x4D659218E32A3268`；代码白名单必须加入 `2.1.195`。
- 主要代码边界：`cc2api/src/service/version_profile.rs`、`rewriter.rs`、`oauth.rs`、`store/db.rs`、`store/settings_store.rs`、`handler/router.rs`、`web/src/components/Settings.vue`。
- 必读规范：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`、backend service/settings/testing 规范。

## Acceptance

- `cc2api` 默认 Claude Code profile 为 `2.1.195`，且 Settings 可展示/选择。
- `/v1/messages` 输出对齐抓包中的 UA、Stainless package/runtime、beta、billing 与 CCH 规则。
- settings 切换到 `2.1.195` 会同步覆盖 `allowed_claude_code_versions` 和所有账号 canonical env。
- 原有 `2.1.187` profile 保留可回滚。
- `cargo fmt --check`、`cargo test`、`cargo test cch` 通过；如改前端，`npm run build` 通过或记录原因。

## Next Step

- 用户确认 planning artifacts 和 brief 后，运行 `task.py start .trellis/tasks/06-29-cc2api-2-1-195-fingerprint-upgrade`，再进入 Phase 2.1 `trellis-route(implement)`。
