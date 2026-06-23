# Release Operations

## Conclusion
Release operations exist.

## SQL Changes
新增并迁移 settings / accounts 相关数据：

- settings 新增 `claude_code_version_profile` 默认值。
- 版本切换时会强制覆盖 `allowed_claude_code_versions`。
- 版本切换时会批量更新账号 `canonical_env.version`、`canonical_env.version_base`、`canonical_env.build_time`。
- SQLite 与 PostgreSQL 路径均需要保持兼容；上线后需要确认真实数据库账号版本分布。

## Configuration Changes
管理员可在系统设置中选择内置 Claude Code 版本画像：

- `2.1.185`
- `2.1.173`

当前线上已切换为 `2.1.173`，对应 `allowed_claude_code_versions=2.1.89-2.1.173`。`allowed_user_agents` 不随版本切换覆盖。

## Batch / Deployment Scripts / Data Repair
已执行远程部署与只读验证：

- 镜像部署到 `ghcr.io/silentflower/claude-code-gateway:latest`。
- 服务已 recreate 并通过 `/` 健康检查。
- 已通过管理 API 与 SQLite WAL 副本检查 settings 和账号 `canonical_env` 分布。

后续如重新发布该功能，需要执行镜像 pull / recreate，并再次检查 settings 与账号版本分布。

## External Systems / Dependent Platforms
涉及远程 cc2api / Claude Code Gateway 实例。上游 Anthropic 请求特征、自动 telemetry 与 GrowthBook payload 会随所选版本画像变化。

## Release Order
1. 发布包含 `cc2api` 版本特征切换的镜像。
2. recreate 网关服务。
3. 在系统设置中选择目标版本画像。
4. 检查 `claude_code_version_profile`、`allowed_claude_code_versions` 和账号 `canonical_env` 分布。
5. 通过安全摘要或定向测试确认 `/v1/messages`、CCH/billing、telemetry/GrowthBook 形态符合目标版本。

## Rollback Notes
可在系统设置中切回另一个内置版本画像；系统会再次同步账号 `canonical_env` 并覆盖 `allowed_claude_code_versions`。

如需代码级回滚，回滚到上一镜像并 recreate 服务。回滚后仍需检查 settings 和账号版本分布，避免运行时画像混用。

## Post-release Verification
按任务验收标准验证：

- Settings 页面可切换 `2.1.185` / `2.1.173`。
- `/admin/settings` 返回目标 profile 和对应 allowed range。
- DB 中所有账号 `canonical_env.version/version_base/build_time` 等于目标画像。
- `/v1/messages` 请求头、billing header、CCH / `cc_version` 与目标版本一致。
- 自动 telemetry 和 GrowthBook payload shape 与目标版本一致。
- 日志中无 `ERROR` / `panic`，且不记录 token、Cookie、Authorization、完整 prompt 或完整响应正文。
