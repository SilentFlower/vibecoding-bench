# Brief — 修复用量窗口跨周期并研究 Fable 被动配额

## Goal

- 修复 cc2api 把上一周期高 utilization 与下一周期新 resets_at 组合成假 99%/100% 的问题，并让 Fable 默认只通过 Anthropic 响应头被动采集；只有 `auto_poll_usage=true` 或管理员手动刷新才调用 usage API。

## Scope

- 扩展 `extract_passive_usage`，解析 5h、7d 和 `7d_oi`，将 `7d_oi` 归一化为现有 `usage_data.seven_day_fable`。
- 在 AccountService 建立统一的 rollover 合并规则，覆盖被动成功响应、429 响应、PrimePoller 和显式主动 usage 查询。
- 对旧 reset 已到期、新 reset 已推进但成功类样本仍携带高位旧值的场景，保存新 reset 并将首次新周期 utilization 置 0；同周期后续有效样本可正常更新。
- 429 按窗口自身状态识别拒绝：真实拒绝窗口保留高 utilization，其他允许窗口仍做 rollover；通用 5h/7d 耗尽继续账号级冷却，Fable `7d_oi` 耗尽只做模型级换号/不可用。
- 删除 Gateway 中 Fable 请求结束后延迟 3 秒刷新 usage 的整条机会式链路及 AccountService 节流状态。
- 保留现有后台 poller 的 `auto_poll_usage` 过滤和管理端手动刷新入口。
- 更新 cc2api backend service spec，并补齐 Gateway、AccountService 和调度回归测试。

## Non-Goals

- 不修改 ai-fund 的用量 JSON 适配或展示字段。
- 不新增数据库 schema、配置开关或未公开的主动探测接口。
- 不在本任务中部署生产环境，也不主动发送消耗额度的探测请求。
- 不删除 usage API 本身；显式主动采集仍然保留。

## Key Context

- 当前被动解析位于 `cc2api/src/service/gateway.rs`，只支持 5h/7d；成功路径持久化，429 路径只用于判断且不持久化。
- 当前直接合并位于 `cc2api/src/service/account.rs::update_passive_usage`，没有比较新旧 reset；`refresh_usage` 也直接覆盖完整 usage_data。
- 当前隐式主动调用由 `FABLE_USAGE_REFRESH_DELAY`、`FableUsageRefreshContext`、SlotGuardBody EOF 触发和 `refresh_usage_after_fable_request` 组成，必须完整删除，不能只改延迟时间。
- 现有 `UsagePollerService` 已严格筛选 active OAuth 且 `auto_poll_usage=true` 的账号，管理端 `POST /admin/accounts/:id/usage` 是显式手动入口，可直接复用。
- 最新 sub2api 已验证 `anthropic-ratelimit-unified-7d_oi-utilization/reset/status/surpassed-threshold`，并将其映射为 `seven_day_fable`；Anthropic 官方文档尚未公开该内部头，缺失时必须兼容且不得隐式补查。
- rollover 保护针对旧 reset 已到期、新 reset 推进、且窗口本身未被拒绝的高位样本；429 中只有明确拒绝窗口不能清零，不能把整份响应一概处理。
- 对外 `/admin/accounts` 字段保持稳定，并保留 `seven_day_sonnet`、`limits`、`spend`、`extra_usage` 等未被当前观察覆盖的数据。

## Acceptance

- 旧窗口 99%/100% 且 reset 已过期时，首个带新 reset 和旧高值的成功样本不会重新对外显示 99%/100%。
- 新周期 utilization 已下降时采用真实值；同一新 reset 的后续完整样本可以继续正常更新。
- 成功和 429 响应中的 `7d_oi` 都能被动写入 `usage_data.seven_day_fable`，缺头或非法头不覆盖已有有效数据。
- Fable `7d_oi` 429 不全局禁用账号；普通 5h/7d 429 行为不回归。
- 普通 Fable 成功与 429 请求均不会调用 usage API。
- `auto_poll_usage=true` 的 active OAuth 账号仍被后台轮询，关闭时不轮询；管理员手动刷新保持可用。
- `cargo fmt --check`、相关定向测试、完整 `cargo test` 和 `git diff --check` 通过。

## Next Step

- 用户确认本 brief 与 planning artifacts 后，运行 `task.py start` 激活任务，再通过 `trellis-route(target=implement)` 进入实现与验证。
