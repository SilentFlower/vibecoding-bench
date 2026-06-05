# brainstorm: cc2api 全局 Claude Code 版本与 UA 访问策略

## Goal

为 cc2api 增加全局访问策略，集中控制客户端请求中的 Claude Code 版本范围和允许访问的 User-Agent 列表，减少不同客户端版本、伪装 UA 混乱导致的上游风险和排查成本。

## Background / Known Context

- 用户反馈：当前客户端请求版本很乱，需要全局设置。
- 需要两个全局配置项：Claude Code 版本号控制，以及允许访问的 UA 列表。
- cc2api 已有 `settings` 表和 `/admin/settings` 读写接口，可复用现有全局配置机制。
- 现有网关入口在 `src/service/gateway.rs` 中读取原始 `User-Agent`，随后识别 `ClientType` 并进行账号选择、请求改写和上游转发。
- 现有客户端识别规则在 `src/service/rewriter.rs`：`User-Agent` 以 `claude-code/` 或 `claude-cli/` 开头时识别为 Claude Code；body metadata 包含 `user_id` 也会识别为 Claude Code。
- 现有设置页在 `web/src/components/Settings.vue`，已经承载评分权重、峰值预热和 `allow_system_role_models`。

## Assumptions

- 默认值应保持向后兼容：未配置时不拒绝现有请求。
- 版本控制主要用于 Claude Code / Claude CLI 类请求；纯 API 客户端可由 UA 白名单单独控制。
- 拒绝应发生在选择账号和请求上游之前，并返回本地 403 或 400，避免消耗账号额度。

## Open Questions

- 已决策：UA 白名单使用前缀/通配匹配，不使用正则。

## Decisions

- UA 白名单配置支持逗号或换行分隔的多个 pattern。
- UA pattern 使用 `*` 通配任意字符，例如 `claude-code/*`、`claude-cli/*`、`curl/*`、`MyClient/1.*`。
- 版本范围配置支持逗号或换行分隔的多个条目。
- 版本范围条目支持精确版本、通配版本和闭区间，例如 `2.1.156`、`2.1.*`、`2.1.150-2.1.180`。
- 默认 Claude Code / CLI 版本范围为 `2.1.89-2.1.156`。
- 默认额外允许的非 Claude Code UA 为 `AI-Hub-Monitor*` 和 `python-httpx*`。

## Requirements

- 管理端可配置允许的 Claude Code 版本范围。
- 管理端可配置允许访问的 User-Agent，支持多个条目。
- User-Agent 允许列表采用 `*` 通配匹配，不支持正则。
- Claude Code 版本范围支持精确版本、`*` 通配和 `min-max` 闭区间。
- 网关在请求入口校验原始客户端 `User-Agent`。
- 不符合策略的请求不请求上游，并返回可读错误。
- 清空配置可关闭对应限制。
- 后端需要校验配置格式，避免错误配置导致不可预期匹配。
- 设置变更后应尽快生效，不要求重启服务。

## Acceptance Criteria

- [ ] `/admin/settings` 可以读取和更新版本范围与 UA 白名单配置。
- [ ] 设置页可以编辑并保存版本范围与 UA 白名单。
- [ ] `claude-code/<version>` / `claude-cli/<version>` 请求会按版本范围校验。
- [ ] UA pattern 如 `claude-code/*`、`MyClient/1.*` 能按 `*` 通配正确匹配。
- [ ] 不在允许 UA 列表内的请求会被本地拒绝，且不会请求上游。
- [ ] 默认配置允许 `claude-code/2.1.89` 到 `claude-code/2.1.156`，拒绝范围外 Claude Code / CLI 版本。
- [ ] 默认配置允许 `AI-Hub-Monitor*` 和 `python-httpx*` 非 Claude Code UA。
- [ ] 增加覆盖版本范围、UA 匹配、拒绝响应的测试。

## Notes

- 该功能影响全局入口策略，落地前需要确认 UA 匹配语义，避免配置能力过强导致误拦截或误放行。
