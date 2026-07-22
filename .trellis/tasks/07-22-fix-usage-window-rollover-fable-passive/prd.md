# 修复用量窗口跨周期并研究 Fable 被动配额

## Goal

修复 cc2api 在 Anthropic 用量窗口跨周期后，可能把上一周期的高 `utilization` 与下一周期的新 `resets_at` 组合展示、调度或持久化的问题；同时将 Fable 独立周窗口改为从上游响应头被动采集。默认请求链路不得主动查询 `/api/oauth/usage`，只有账号显式开启 `auto_poll_usage` 或管理员手动刷新时才允许调用。

## Background

- cc2api 当前被动采集只解析 `anthropic-ratelimit-unified-5h-*` 与 `anthropic-ratelimit-unified-7d-*`，未解析 Fable 独立窗口 `7d_oi`。证据：`cc2api/src/service/gateway.rs:5068-5115`。
- 当前 `update_passive_usage` 直接覆盖同名窗口，没有比较已有与新 `resets_at` 的周期关系。证据：`cc2api/src/service/account.rs:1283-1303`。
- 当旧窗口已过期、下一次响应把 `resets_at` 推进到下一周期，但 `utilization` 仍残留上一周期高值时，现有前端和调度逻辑会重新把该窗口视为高用量。
- cc2api 当前对成功的 OAuth Fable `/v1/messages` 请求，在响应 body EOF 后延迟 3 秒主动刷新 usage，并按账号做 60 秒节流。这是为补齐 Fable scoped quota，不是通用跨周期一致性机制。
- 最新 sub2api `main`（本地已 fast-forward 到 `63cef6059`）被动解析：
  - `anthropic-ratelimit-unified-7d_oi-utilization`
  - `anthropic-ratelimit-unified-7d_oi-reset`
  - `anthropic-ratelimit-unified-7d_oi-status`
  - `anthropic-ratelimit-unified-7d_oi-surpassed-threshold`
- sub2api 将 `7d_oi` 映射为 `seven_day_fable`，并在 429 时仅对 Fable 模型族设置模型级限流，不把整个账号全局限流。证据：`backend/internal/service/ratelimit_service.go:1268-1335,1685-1730`。
- Anthropic 官方公开文档未说明 `7d_oi` 内部响应头；公开 Claude Code 问题和开源网关代码能确认 unified headers 的实际存在，因此该协议需要以兼容性解析和缺失降级方式接入。

## Requirements

- R1：cc2api 必须被动解析通用 5h、通用 7d 与 Fable `7d_oi` 窗口，并将 `7d_oi` 归一化为现有 `usage_data.seven_day_fable`。
- R2：窗口跨周期时，不得把上一周期已到期的高利用率直接带入下一周期。至少覆盖：旧 `resets_at <= now`，新 `resets_at > old resets_at`，且首个新周期响应仍携带旧高利用率的场景。
- R3：跨周期保护必须同时适用于 `five_hour`、`seven_day` 与 `seven_day_fable`，并保持现有 `seven_day_sonnet` 主动 usage 数据不被被动更新误删。
- R4：成功响应与 429 响应只要携带完整窗口头，都应能被动持久化；429 必须按各窗口自身的 `status` / `surpassed-threshold` 判定是否拒绝，不能把整份响应中的其他允许窗口一并视为耗尽。Fable `7d_oi` 耗尽只影响 Fable 模型族，不应全局禁用账号。
- R5：响应头缺失、非法、时间戳异常或不完整时，不得覆盖已有有效窗口。
- R6：现有 SetupToken 与 OAuth 账号均可消费被动窗口；主动 usage 能力仅限 OAuth 的约束保持不变。
- R7：不得在 Gateway 热路径同步调用 usage API。
- R8：保留现有 API JSON 字段名称，避免管理页、调度器和 ai-fund 适配层发生破坏性变更。
- R9：删除“Fable 请求成功或 429 后延迟刷新 usage”的机会式主动采集链路及其账号级节流状态。普通业务请求无论成功或失败，都不得因为 Fable 自动调用 usage API。
- R10：主动 usage 查询只保留两个显式入口：`auto_poll_usage=true` 的 OAuth 账号由现有后台轮询器定时查询，以及管理员手动调用刷新接口；不得新增隐式兜底。

## Acceptance Criteria

- [ ] 旧窗口 `utilization=100` 且 `resets_at` 已过期，首个新周期响应携带新 reset 与旧高值时，持久化和对外返回不得重新显示 100%。
- [ ] 同一新周期后续响应携带有效利用率时，可以恢复按响应头真实值更新。
- [ ] `7d_oi utilization/reset` 能被动写入并通过 `/admin/accounts` 作为 `usage_data.seven_day_fable` 返回。
- [ ] Fable `7d_oi` 429 只触发模型级不可用或换号，不把账号对非 Fable 模型全局隔离。
- [ ] 普通 5h/7d 429 和现有限流行为不回归。
- [ ] 单个窗口触发 429 时，响应中其他 `status=allowed` 的高位窗口仍执行 rollover 保护，不参与本次限流分类。
- [ ] 缺少 `7d_oi` 头时保持兼容，不产生空窗口或覆盖现有有效 Fable 数据。
- [ ] 普通 Fable 成功响应和 429 响应均不会触发任何 usage API 请求。
- [ ] `auto_poll_usage=true` 的 OAuth 账号仍会被现有后台轮询器刷新，`auto_poll_usage=false` 的账号不会被轮询。
- [ ] 管理员手动刷新 usage 的接口行为保持不变。
- [ ] Rust 格式检查、相关单测、完整 `cargo test` 通过。

## Out of Scope

- 修改 Anthropic 上游协议或依赖未公开接口以外的新网络调用。
- 修改 ai-fund 的展示契约；ai-fund 继续读取 cc2api 归一化后的 `usage_data`。
- 部署生产环境或主动发送消耗额度的探测请求。
