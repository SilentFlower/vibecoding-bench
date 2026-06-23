# 隐藏 UA 允许名单错误详情

## Goal

当 `cc2api` 拒绝不在允许范围内的客户端 `User-Agent` 时，外部错误响应不得暴露管理员配置的允许 UA 规则列表，避免把访问策略细节返回给未授权客户端。

## Requirements

- 对非 Claude Code / CLI 客户端，如果 `User-Agent` 未命中 `allowed_user_agents`，HTTP 响应中的错误文案必须返回当前请求的 `User-Agent`，便于调用方自查。
- `allowed_user_agents` 未命中的响应不得包含 `allowed_user_agents` 的原始配置值或任何允许规则列表。
- 本次不隐藏 `allowed_claude_code_versions` 的允许范围，Claude Code / CLI 版本未命中的错误文案保持现状。
- 响应仍需保持现有 403 状态码和标准错误对象结构，调用方仍能识别这是访问策略拒绝。
- 配置校验失败属于管理员输入错误，不在本需求范围内，仍可返回具体配置错误以便管理端修正。
- 现有允许逻辑不能改变：已允许的 UA 继续放行，空白名单继续保持兼容行为。
- 需要补充或调整测试，覆盖未命中 UA 时响应不泄露允许规则。

## Acceptance Criteria

- [ ] `allowed_user_agents` 未命中时，响应体包含当前请求的 `User-Agent`。
- [ ] `allowed_user_agents` 未命中时，响应体不包含允许规则列表、具体 pattern 或 `允许规则` 这类引导性文案。
- [ ] `allowed_user_agents` 未命中时，响应仍为 403，并保留可机器识别的错误 code / setting。
- [ ] 默认允许的 `AI-Hub-Monitor*`、`python-httpx*` 以及自定义允许规则的匹配行为不回退。
- [ ] 相关 Rust 测试通过。

## Notes

- 代码定位：`cc2api/src/service/access_policy.rs` 中 `AccessPolicy::check_user_agent` 当前会在非 Claude Code UA 未命中时返回 `允许规则：{raw_user_agents}`。
- 用户已确认：同文件中 Claude Code / CLI 版本未命中的 `允许范围：{raw_versions}` 不需要隐藏。
- 用户已补充：非 Claude Code / CLI 的当前请求 UA 需要返回，隐藏范围只针对允许列表/规则。
