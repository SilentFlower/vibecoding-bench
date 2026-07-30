# 控制 cc2api Fable 周额度使用上限

## Goal

为 cc2api 的 Fable 请求增加可配置的全局周用量硬上限。当 OAuth 账号最近观测到的 Fable 周用量达到管理员设定值后，不再向该账号分配新的 Fable 请求，从而默认保留约一半周额度。

## Background

- 当前 Fable 调度只把 `seven_day_fable.utilization >= 100` 且 `resets_at` 仍在未来的 OAuth 账号视为明确耗尽；命中后才会跳过该账号或打破 sticky 选择其他账号（`cc2api/src/service/account.rs:48`、`cc2api/src/service/account.rs:960`、`cc2api/src/service/account.rs:2161`）。
- 当前策略由全局 setting `fable_sticky_quota_fallback_enabled` 控制，并在 Gateway 内存中热加载（`cc2api/src/service/gateway.rs:408`、`cc2api/src/service/gateway.rs:707`）。
- 账号综合评分使用通用 `seven_day`、`five_hour` 和并发负载，不包含 `seven_day_fable`（`cc2api/src/service/account.rs:1822`）；本任务不改变该排序规则。
- 2026-07-09 的既有决策拒绝把固定 `97%` 隐式当作耗尽线。本任务改为新增管理员可见、可配置的产品规则，而不是修改通用 `USAGE_HIT_THRESHOLD`。

## Requirements

- 新增全局 setting `fable_weekly_usage_limit_percent`，值为 `1～100` 的整数，默认值为 `50`。
- 所有 OAuth 账号共用同一控制线，不增加账号级字段或独立阈值。
- 现有 `fable_sticky_quota_fallback_enabled` 继续作为总开关：开启时执行百分比限制，关闭时不按 Fable 周用量过滤账号。
- 控制仅作用于 `/v1/messages` 的 `claude-fable-5` 与 `claude-fable-5[...]` 请求；非 Fable 请求、SetupToken 账号和其他入口不受影响。
- 只有 `usage_data.seven_day_fable.utilization` 为合法数字，且 `resets_at` 是未来 RFC3339 时间时，才依据该窗口执行限制；缺失、非法或过期窗口继续允许调度。
- 最近观测用量 `>= fable_weekly_usage_limit_percent` 的账号不再承载新的 Fable 请求。
- sticky 命中达到上限的账号时，本轮尝试其他符合 API Token 账号范围且未达到上限的账号；没有替代账号时返回明确的 429，并保留原 sticky 绑定。
- 非 sticky 选号需要过滤达到上限的账号；所有候选均达到上限时返回明确的 429，不得静默回退到已达到上限的账号。
- 未达到上限的账号继续沿用现有 sticky、账号优先级、通用 7 天/5 小时用量和并发评分，不新增 Fable 用量排序、加权或主动均衡。
- 配置保存后热生效，不要求重启 cc2api。已有部署升级后若不存在新 key，通过 settings 默认插入获得 `50`。
- 控制依据请求开始前最近一次已采集的用量；低于控制线时允许当前请求。若单次请求使实际用量略微越线，则从后续请求开始拦截。
- 不预测单次请求消耗，也不设置固定安全缓冲。

## Acceptance Criteria

- [ ] 管理端可以读取、修改并保存 `1～100` 的 Fable 周用量上限；`0`、`101`、小数和非数字值被拒绝。
- [ ] 默认配置为开关开启、上限 `50%`，保存新值后新的 `/v1/messages` Fable 请求立即按新值调度。
- [ ] sticky OAuth 账号达到控制线后，有其他未达到控制线的候选账号时选择替代账号，并沿用现有成功承载后重绑 sticky 的机制。
- [ ] sticky 账号达到控制线但没有替代账号时返回 429，旧 sticky 绑定仍保留。
- [ ] 非 sticky Fable 请求过滤达到控制线的账号；所有允许账号均达到控制线时返回 429。
- [ ] 已观测用量低于控制线时不提前过滤；单次请求造成少量越界后，更新后的用量会阻止后续 Fable 请求。
- [ ] 总开关关闭时不执行百分比限制；配置为 `100` 时兼容此前“明确耗尽才切换”的行为。
- [ ] 非 Fable 请求、SetupToken 账号、过期或不完整的 Fable usage 窗口保持既有行为。
- [ ] 未达到控制线时，现有 sticky、RPM 和账号综合评分选择行为不发生变化。
- [ ] 后端设置默认值、校验、数据库补齐、启动加载和管理端热刷新均有回归覆盖，前端构建通过。

## Out Of Scope

- 不改变 Fable usage 的主动/被动采集协议。
- 不改变非 Fable 模型的通用 7 天、5 小时用量评分和 429 冷却规则。
- 不按 `seven_day_fable` 对未达到上限的账号进行排序、加权或主动均衡。
- 不引入按账号、API Token 或用户分别配置上限的能力。
- 不引入单次请求额度预测、预留缓冲或新的计费系统。
