# cc2api 版本特征切换 - 实施计划

## Checklist

1. 读取任务文档与 cc2api backend/frontend/protocol spec。
2. 在 `src/service/version_profile.rs` 新增内置 profile registry 和 helper：
   - profile key 列表；
   - 默认 profile；
   - `profile_for_key` / `validate_profile_key`；
   - `profile_for_version` / `all_profiles`；
   - 每个 profile 显式声明 identity、access_policy、request、billing、telemetry、endpoint 子画像；
   - `2.1.173` 的 GrowthBook UA 为 `Bun/1.3.14`，telemetry shape 为 `ClaudeCode2173`；
   - `2.1.185` 的 GrowthBook UA 为 `Bun/1.4.0`，telemetry shape 为 `ClaudeCode2185`。
3. 在 settings 默认值与 DB migration 中新增 `claude_code_version_profile=2.1.185`。
4. 在 `AccountStore` 或合适 store/service 层新增批量更新账号 `canonical_env.version/version_base/build_time` 的方法，覆盖 SQLite 和 PostgreSQL。
5. 修改 Settings 保存逻辑：
   - 校验 `claude_code_version_profile`；
   - 保存该 key 时强制覆盖 `allowed_claude_code_versions`；
   - 不因版本切换覆盖 `allowed_user_agents`；
   - 成功后 reload access policy。
6. 修改新账号创建逻辑，使 `canonical_env` 使用当前 profile，而不是固定编译期默认画像。
7. 修改 `GET /admin/settings` 返回默认 `claude_code_version_profile`。
8. 修改 Settings 前端：
   - 增加版本特征选择控件；
   - 保存 payload 包含 `claude_code_version_profile`；
   - UI 说明覆盖账号 env 和 `allowed_claude_code_versions`，不覆盖 `allowed_user_agents`。
9. 改造 telemetry 调用点：
   - event logging UA 继续按账号版本；
   - GrowthBook UA 从 profile 读取；
   - event logging payload 根据 `TelemetryShape` 切换 `email`、`betas`、`additional_metadata`、env 扩展字段；
   - GrowthBook payload 根据 `TelemetryShape` 切换 `email`、`forcedFeatures`、`forcedVariations`、`url`。
10. 补 Rust 单测：
   - profile key 校验和默认值；
   - profile key 唯一、必填字段非空；
   - settings 保存未知 profile 返回错误；
   - 切换 profile 后账号 canonical env 批量更新；
   - `allowed_claude_code_versions` 被覆盖，`allowed_user_agents` 保留；
   - 新账号使用当前 profile；
   - rewriter/telemetry 对 `2.1.173` 与 `2.1.185` 使用账号 env 版本。
   - `2.1.173` telemetry 使用旧 shape：GrowthBook UA `Bun/1.3.14`、event payload 保留旧字段形态。
   - `2.1.185` telemetry 使用新 shape：GrowthBook UA `Bun/1.4.0`、event payload 使用 `014c0e5` 的字段形态。
11. 如必要更新 README 中版本画像切换说明和新增版本流程。
12. 运行验证命令。

## Validation Commands

```bash
cd cc2api
cargo fmt --check
cargo test
cargo test cch
```

如修改前端：

```bash
cd cc2api/web
npm run build
```

## Risky Files

- `cc2api/src/service/version_profile.rs`
- `cc2api/src/handler/router.rs`
- `cc2api/src/store/db.rs`
- `cc2api/src/store/account_store.rs`
- `cc2api/src/service/account.rs`
- `cc2api/src/service/rewriter.rs`
- `cc2api/src/service/telemetry.rs`
- `cc2api/web/src/components/Settings.vue`
- `cc2api/web/src/api.ts`

## Rollback Points

- 若账号批量 env 更新在 PostgreSQL/SQLite 任一侧实现不稳，先停止实现并修复 store 层测试，不能留下只支持 SQLite 的切换。
- 若为了赶进度出现 `if version == "2.1.173"` 散落在 telemetry/rewriter，应回到 profile registry 重构，不能把可扩展设计退化成临时分支。
- 若前端保存 payload 与后端强制覆盖冲突，以后端返回和实际 settings 为准，前端保存成功后重新加载 settings。

## Implementation Result

- 已在 `version_profile.rs` 建立内置版本画像注册表，首批支持 `2.1.185` 与 `2.1.173`，并集中声明 identity、access policy、request、billing、telemetry、endpoint 子画像。
- 已新增 `claude_code_version_profile` setting；保存 profile 时以事务同步账号 canonical env、写入 profile key，并强制覆盖 `allowed_claude_code_versions`，不覆盖 `allowed_user_agents`。
- 新账号创建会按当前 profile 覆盖 `canonical_env.version/version_base/build_time`。
- 请求重写与自动 telemetry 均按账号 env.version 映射到 profile；GrowthBook UA 与 telemetry/GrowthBook payload shape 支持 `2.1.173` / `2.1.185` 切换。
- Settings 页面已新增 Claude Code 版本特征选择控件，并将版本范围改为后端强制覆盖后的只读回显。
- 修复了 `account_scheduler_test` 中 sticky RPM 用例跨分钟窗口导致的并行不稳定。

## Validation Result

```bash
cd cc2api
cargo fmt --check
cargo test
cargo test cch
git diff --check
cd web && npm run build
```

以上命令均已通过。
