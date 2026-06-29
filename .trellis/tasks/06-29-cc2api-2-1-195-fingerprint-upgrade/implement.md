# 实施计划

## Step 1：安全证据与任务上下文

- [x] 从远程服务器拉取 run `23594999fa77` 抓包。
- [x] 将原始证据放到任务本地 `evidence/` 并通过 `.gitignore` 排除。
- [x] 生成脱敏摘要 `research/run-23594999fa77-summary.md`。
- [x] 复算 `cc_version`：30/30 命中。
- [x] 复算 CCH：30/30 命中 `2.1.172+` 规则。

## Step 2：更新版本画像

- [x] 在 `cc2api/src/service/version_profile.rs` 新增 `PROFILE_2_1_195`。
- [x] 将默认 profile、默认版本、默认 build time、默认 allowed range 指向 `2.1.195`。
- [x] 将 `STAINLESS_RUNTIME_VERSION` 更新为 `v26.3.0`。
- [x] 更新 profile registry 单测与差异单测。

## Step 3：更新 CCH / cc_version 覆盖

- [x] 在 `cch_attestation_input` 与 `cch_attestation_seed` 中加入 `2.1.195`。
- [x] 补充 `2.1.195` 的 CCH seed 与 top-level 规范化测试。
- [x] 补充 `cc_version` 后缀样本测试，覆盖 Haiku `113` 和 Opus `aff`。

## Step 4：更新 settings / DB / 账号迁移

- [x] 确认 `PREVIOUS_ALLOWED_CLAUDE_CODE_VERSIONS_SETTINGS` 覆盖 `2.1.89-2.1.187`。
- [x] 更新默认 settings 测试，确认旧默认升级到 `2.1.89-2.1.195`。
- [x] 更新账号 canonical env 迁移测试，确认 `version/version_base/build_time` 到 `2.1.195`。
- [x] 更新 profile-only settings payload 测试，确认 access policy reload 仍触发。

## Step 5：更新前端 Settings

- [x] `cc2api/web/src/components/Settings.vue` fallback 默认 profile 改为 `2.1.195`。
- [x] 默认 allowed range 和 placeholder 同步到 `2.1.89-2.1.195`。
- [x] 确认后端 profiles 返回时前端显示新 profile。

## Step 6：验证

- [x] `cd cc2api && cargo fmt --check`
- [x] `cd cc2api && cargo test`
- [x] `cd cc2api && cargo test cch`
- [x] 如修改前端：`cd cc2api/web && npm run build`
- [x] `git status --short` 确认未纳入 `evidence/` 原始抓包。

## 风险文件

- `cc2api/src/service/version_profile.rs`
- `cc2api/src/service/rewriter.rs`
- `cc2api/src/service/oauth.rs`
- `cc2api/src/store/db.rs`
- `cc2api/src/store/settings_store.rs`
- `cc2api/src/handler/router.rs`
- `cc2api/web/src/components/Settings.vue`

## 实施前检查

- 读取 `prd.md`、`design.md`、`implement.md`。
- 读取 `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`。
- 读取 `.trellis/spec/cc2api/backend/service-architecture.md`、`settings-database.md`、`testing-quality.md`。
- 若进入实现阶段，先走 Phase 1.4 任务 brief 审阅与 `task.py start`，再走 Phase 2.1 `trellis-route(implement)`。
