# cc2api 升级 Claude Code 2.1.187 画像 - 实施计划

## Ordered Checklist

1. 更新 `cc2api/src/service/version_profile.rs`
   - 新增 `PROFILE_2_1_187`。
   - 默认 profile / 默认常量切到 `2.1.187`。
   - `CLAUDE_CODE_PROFILES` 增加 `2.1.187` 并保留 `2.1.185`、`2.1.173`。
   - 更新 profile 相关单测。

2. 更新 CCH / `cc_version` 覆盖
   - `cc2api/src/service/rewriter.rs` 的 `cch_attestation_input()` 增加 `2.1.187`。
   - `cch_attestation_seed()` 增加 `2.1.187`。
   - 增加或更新 CCH、`cc_version`、header、telemetry/GrowthBook 断言。
   - 不把 `structured-outputs-2025-12-15` 加入通用主请求 beta。

3. 修复启动迁移一致性
   - 调整 `cc2api/src/store/db.rs` 的 `upgrade_default_settings()` / `upgrade_account_claude_code_profile()`。
   - 迁移按 `settings.claude_code_version_profile` 选择目标 profile。
   - 默认 profile 缺失时升级到 2.1.187。
   - 已显式选择 `2.1.185` / `2.1.173` 时，重启迁移不得写回默认 profile。
   - 补 SQLite 单测；如实现 SQL 分支改动涉及 PG 语法，手工核对 PostgreSQL SQL。

4. 更新 Settings 前端 fallback
   - `cc2api/web/src/components/Settings.vue` 默认值和 fallback profile 列表改为包含 2.1.187。
   - placeholder / allowed range fallback 同步为 `2.1.89-2.1.187`。
   - 保持后端返回 profile 列表为主要真相。

5. 检查其它硬编码
   - 搜索 `2.1.185`、`2.1.89-2.1.185`、`2.1.187`、`ClaudeCode2185`。
   - 只更新默认值和测试断言；保留历史 profile 本身的 2.1.185 字段。
   - 确认 `allowed_user_agents` 不被版本切换覆盖。

## Validation Commands

后端：

```bash
cd cc2api
cargo fmt --check
cargo test
cargo test cch
```

前端（如改动 `cc2api/web`）：

```bash
cd cc2api/web
npm run build
```

可选定向检查：

```bash
cd cc2api
cargo test version_profile
cargo test migrate
cargo test growthbook
cargo test event_batch
```

## Risky Files / Rollback Points

- `cc2api/src/service/version_profile.rs`：默认 profile 的单一真相。
- `cc2api/src/service/rewriter.rs`：CCH 分支和请求 header/body 改写。
- `cc2api/src/service/telemetry.rs`：默认 identity 进入 telemetry / GrowthBook 的断言。
- `cc2api/src/store/db.rs`：启动迁移最容易造成 settings 与账号 env 不一致。
- `cc2api/src/store/settings_store.rs`：Settings 保存 profile 的事务路径。
- `cc2api/web/src/components/Settings.vue`：前端 fallback 列表。

如实现中发现抓包结论与代码可测行为冲突，先回到 planning 更新 `research` / `design.md`，不要直接扩大实现范围。

## Context Manifest

实施前 sub-agent 需要读取：

- `prd.md`
- `design.md`
- `implement.md`
- `research/cc2api-2-1-187-capture-summary.md`
- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`
- `.trellis/spec/cc2api/backend/settings-database.md`
- `.trellis/spec/cc2api/backend/testing-quality.md`
- `.trellis/spec/cc2api/frontend/frontend-guidelines.md`

## Start Gate

当前任务仍处于 `planning`。用户审阅并明确同意开始实现后，再执行 `task.py start`，随后按 Trellis routing 选择实现模式。
