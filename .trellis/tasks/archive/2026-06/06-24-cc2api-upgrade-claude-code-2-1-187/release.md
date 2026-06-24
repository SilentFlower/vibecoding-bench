# Release Operations

## Conclusion
Release operations exist.

## SQL Changes
None. 本次代码包含启动迁移逻辑调整，但不需要人工执行 SQL。

## Configuration Changes
None. 默认 Claude Code 画像随代码升级为 `2.1.187`，管理员仍可在 Settings 中切回 `2.1.185` 或 `2.1.173`。

## Batch / Deployment Scripts / Data Repair
None.

## External Systems / Dependent Platforms
需要发布 `cc2api` 服务镜像或二进制，使默认画像、启动迁移、Settings 展示和前端构建产物生效。

## Release Order
1. 发布包含 `cc2api` commit `3d172c0` 的服务版本。
2. 启动服务后让内置迁移按当前 `settings.claude_code_version_profile` 同步账号 `canonical_env`。

## Rollback Notes
可先在 Settings 中切回 `2.1.185` 或 `2.1.173`；如需回滚代码，确认旧代码是否理解 `2.1.187` profile，必要时先显式切回旧 profile 再回滚服务版本。

## Post-release Verification
按任务验收标准验证：Settings 默认显示 `2.1.187`，版本范围为 `2.1.89-2.1.187`，请求 UA / beta / `cc_version` / CCH / telemetry / GrowthBook 与抓包摘要一致；旧 profile 重启后不被默认画像覆盖。
