# Brief — 控制 cc2api Fable 周额度使用上限

## Goal

- 为 cc2api 的 Fable 请求增加全局周用量硬上限；默认在 OAuth 账号最近观测用量达到 `50%` 后停止向该账号分配新的 Fable 请求。

## Scope

- 新增全局 setting `fable_weekly_usage_limit_percent`，仅允许 `1～100` 整数，默认 `50`；已有 `fable_sticky_quota_fallback_enabled` 继续作为总开关。
- 同步 settings 默认值、数据库补齐、管理 API 读取与校验、Gateway 启动加载和保存后热刷新。
- 扩展 `AccountSelectionContext`，让 `/v1/messages` 的 Fable 账号选择使用配置阈值。
- sticky 或非 sticky OAuth 账号达到阈值时跳过该账号；无替代账号时返回 429，sticky 绑定保留。
- 在现有 Settings 页面 Fable 小节增加百分比输入、前端校验和准确说明文案。
- 补充阈值边界、开关、模型/账号范围、异常 usage、settings 和数据库默认值回归测试。

## Non-Goals

- 不改变 Fable usage 的采集协议、usage JSON 或账号 DTO。
- 不改变阈值以下的 sticky、RPM、优先级和通用评分，也不按 Fable 用量主动均衡账号。
- 不增加账号级、API Token 级或用户级阈值。
- 不预测单次请求消耗，不承诺实际用量绝不轻微越过控制线。
- 不改变非 Fable 模型的通用 5 小时/7 天限流和账号冷却规则。

## Key Context

- 当前固定语义是 `seven_day_fable.utilization >= 100` 且 reset 在未来才视为耗尽；本任务把该判断泛化为管理员可见的配置阈值，不复用通用 `97%` 撞墙线。
- 控制仅适用于 `/v1/messages` 的 `claude-fable-5` 和 `claude-fable-5[...]`，且仅过滤 OAuth 账号；SetupToken、非 Fable 和其他入口保持原行为。
- usage 缺失、非法或 reset 已过期时继续允许调度，避免脏缓存误伤账号。
- 请求开始时低于阈值即可执行；若该请求使实际用量略微越线，更新后的 usage 从下一请求开始生效。
- 默认 `50%` 会改变升级后开启总开关的实例；设置为 `100` 或关闭现有总开关可热回滚。
- 主要改动位于 `settings_store.rs`、`db.rs`、`router.rs`、`main.rs`、`gateway.rs`、`account.rs`、`Settings.vue` 和调度测试。

## Acceptance

- 管理 API 和页面只接受 `1～100` 整数，拒绝 `0`、`101`、小数和非数字；默认值为 `50`，保存后立即生效。
- 阈值 `50` 时，49% 的合法窗口继续沿用原账号，50% 的 OAuth 账号被过滤；阈值 `100` 时恢复此前 99% 允许、100% 过滤的语义。
- 有替代账号时正确切换并沿用成功承载后重绑 sticky 的机制；无替代账号或所有候选达到阈值时返回可识别的 429。
- 总开关关闭、非 Fable、SetupToken、过期或不完整窗口不受百分比限制。
- 通用 5h/7d、Fable 429、credit、RPM 和阈值以下综合评分行为不回归。
- `cargo fmt --check`、`cargo test`、`npm run build` 和 `git diff --check` 通过。

## Next Step

- 实现与 full Check-All 已完成；下一步由 auto-loop 同步项目规范并执行 commit-only 本地提交。
