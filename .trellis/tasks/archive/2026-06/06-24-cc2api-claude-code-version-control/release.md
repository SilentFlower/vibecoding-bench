# Release Operations

## Conclusion
Release operations exist.

## SQL Changes
None

## Configuration Changes
- 新增全局 setting `blocked_claude_code_versions`，默认值为空字符串。
- 发布后老数据库会通过迁移补齐默认 setting key。
- `claude_code_version_profile` 继续控制允许版本范围；禁止版本配置由管理员按需填写。

## Batch / Deployment Scripts / Data Repair
None

## External Systems / Dependent Platforms
- 需要发布 `cc2api` 网关服务，使访问策略、Settings 页面、Claude Code 2.1.187 协议画像和 telemetry/env 画像修复生效。

## Release Order
1. 部署 `cc2api` 后端和嵌入的前端资源。
2. 启动后确认迁移已执行，老库存在 `blocked_claude_code_versions` 默认 key。
3. 如需拦截特定 Claude Code / CLI 版本，再通过管理端配置禁止版本规则。

## Rollback Notes
Rollback code only. 如已配置 `blocked_claude_code_versions` 导致误拦截，可先清空该 setting。

## Post-release Verification
- `GET /admin/settings` 返回 `blocked_claude_code_versions` 字段。
- 保存合法禁止版本规则后，Gateway 热路径立即生效，不需要重启。
- 命中禁止规则的 `claude-code/` 或 `claude-cli/` 请求返回 403，错误体包含 `blocked_claude_code_versions`。
- 非 Claude Code / CLI User-Agent 不受禁止版本规则影响。
- Claude Code event logging 中 `env.version`、`env.version_base`、`env.build_time`、`shell` 和 `is_running_with_bun` 与目标画像一致。
