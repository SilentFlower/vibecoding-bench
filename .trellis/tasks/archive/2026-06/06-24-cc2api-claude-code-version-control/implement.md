# cc2api Claude Code 版本升级控制 - Implement

## Checklist

1. 更新访问策略核心：
   - 在 `AccessPolicy` 中新增 `blocked_version_rules` 和 `raw_blocked_versions`。
   - 将 `AccessPolicy::parse` 扩展为接收 `allowed_versions`、`blocked_versions`、`allowed_user_agents`。
   - 抽出带 setting 名称的版本规则校验函数，保留 `validate_claude_code_versions` 兼容现有允许列表。
   - 新增 `validate_blocked_claude_code_versions`。
   - 在 `check_user_agent` 中先判断禁止规则，再判断允许规则。

2. 更新 settings 默认值和迁移：
   - 在 `settings_store.rs` 新增 `DEFAULT_BLOCKED_CLAUDE_CODE_VERSIONS_SETTING`。
   - 在 `db.rs` 默认 settings 插入列表加入 `blocked_claude_code_versions`。
   - 增加 migrate 测试，确认老库会得到默认空值。

3. 更新管理 API：
   - `router.rs` import 新校验函数和默认值。
   - `get_settings` 对缺失的 `blocked_claude_code_versions` 回填空字符串。
   - `update_settings` 校验 `blocked_claude_code_versions`。
   - 保存禁止列表后触发 `gateway_svc.reload_access_policy()`。
   - 确认 `apply_claude_code_profile` 仍不覆盖禁止列表。

4. 更新 Gateway 热刷新：
   - `GatewayService::new` 用默认允许列表、默认禁止列表、默认 UA 创建 `AccessPolicy`。
   - `reload_access_policy` 读取 `blocked_claude_code_versions` 并传给 `AccessPolicy::parse`。

5. 更新前端设置页：
   - 新增 `blockedClaudeCodeVersions` ref。
   - 新增 `isValidBlockedClaudeCodeVersions` 校验，或抽出复用的版本规则校验函数。
   - `loadSettings` 读取 `data.blocked_claude_code_versions ?? ''`。
   - `saveSettings` 校验并提交 `blocked_claude_code_versions`。
   - 在“客户端访问策略”卡片中新增文本域和说明文案。

6. 更新文档：
   - README 客户端访问策略段落新增 `blocked_claude_code_versions`。
   - 明确禁止规则优先级和允许列表为空时仍生效。

7. 补测试：
   - `access_policy.rs` 单测覆盖 PRD acceptance 中的版本规则行为。
   - `settings_store.rs` 单测覆盖 profile 切换保留禁止列表。
   - `db.rs` 单测覆盖默认 key 插入。

## Validation Commands

```bash
cd cc2api
cargo fmt --check
cargo test access_policy
cargo test settings_store
cargo test db
cargo test
```

```bash
cd cc2api/web
npm run build
```

## Risky Files

- `cc2api/src/service/access_policy.rs`：入口访问控制，必须保证默认行为不变。
- `cc2api/src/handler/router.rs`：settings 保存流程中 profile 切换会改写 body，新增 key 不能被误处理。
- `cc2api/src/service/gateway.rs`：热路径使用内存缓存，漏 reload 会导致保存后不生效。
- `cc2api/web/src/components/Settings.vue`：设置页字段多，新增校验不能阻断无关设置保存。

## Rollback Points

- 如果访问策略扩展引入兼容风险，先保留新增 setting 默认空值，并让 `AccessPolicy` 在禁止列表为空时完全走旧逻辑。
- 如果前端布局风险较高，优先交付后端 setting 和 API，前端只在现有卡片中增加最小文本域。

## Before Start

- 任务必须从 `planning` 切到 `in_progress` 后才能实现。
- 实现前按 Trellis 流程进入 Phase 2.1，并通过 `trellis-route(implement)` 选择执行模式。
