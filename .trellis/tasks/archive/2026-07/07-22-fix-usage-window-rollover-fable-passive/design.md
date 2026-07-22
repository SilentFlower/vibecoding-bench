# 技术设计

## 设计目标

在不改变 `/admin/accounts` 用量 JSON 字段的前提下，统一修复 5h、7d、Fable 7d 窗口跨周期时的旧值带入问题，并让 Fable 默认完全依赖 Anthropic 响应头被动采集。Gateway 普通请求不再触发 usage API；显式主动采集继续复用现有 `auto_poll_usage` 和管理端手动刷新入口。

## 影响边界

- `cc2api/src/service/gateway.rs`
  - 扩展 Anthropic unified header 解析，增加 `7d_oi -> seven_day_fable`。
  - 成功响应和 429 响应都提交被动用量观察。
  - 删除 Fable 响应结束后延迟 3 秒刷新 usage 的上下文、spawn 和判断 helper。
- `cc2api/src/service/account.rs`
  - 删除机会式 usage 刷新及账号级节流状态。
  - 为主动、被动用量写入提供统一的跨周期合并规则。
  - 保留 `seven_day_sonnet`、`limits`、`spend` 等未被本次观察覆盖的字段。
- `cc2api/src/service/prime_poller.rs`
  - 成功与 429 都按明确观察类型写入响应头用量，不再跳过 429。
- `cc2api/src/service/usage_poller.rs`、`cc2api/src/handler/router.rs`
  - 行为保持：只轮询 `auto_poll_usage=true` 的 active OAuth 账号；手动接口仍可显式刷新。
- `.trellis/spec/cc2api/backend/service-architecture.md`
  - 将旧的“Fable 请求结束后必须主动刷新”契约改为 `7d_oi` 被动采集契约。

## 响应头归一化

`extract_passive_usage` 继续只输出与 usage API 相同的稳定窗口对象：

```text
anthropic-ratelimit-unified-5h-*    -> five_hour
anthropic-ratelimit-unified-7d-*    -> seven_day
anthropic-ratelimit-unified-7d_oi-* -> seven_day_fable
```

每个窗口只有在 `utilization` 与 `reset` 同时存在且可解析时才生成。`utilization` 从 0~1 比例转换为百分比；非有限数值、负值、非法时间和明显超出窗口尺度的 reset 不写入。`status` 与 `surpassed-threshold` 不作为新的管理 API 字段暴露，但 429 路径必须用它们建立窗口级拒绝集合：`status=rejected` 为拒绝，`status=allowed` 为允许；缺少明确状态时再用 `surpassed-threshold=true/正数` 或 `utilization >= 1.0` 兼容旧响应。

## 统一写入与跨周期保护

新增内部观察类型，区分：

- `Allowed`：普通成功响应、PrimePoller 成功响应、显式 usage API 查询结果。
- `RejectedWindows`：上游 429 响应中明确拒绝的窗口集合。

所有用量写入先读取账号已有 `usage_data`，再逐窗口合并。对 `five_hour`、`seven_day`、`seven_day_fable` 使用相同规则：

1. 新窗口不完整或非法时保留旧值。
2. reset 未变化时接受新 utilization。
3. 旧 reset 已到期、且新 reset 推进到下一周期时，判定发生 rollover。
4. `Allowed` rollover 样本如果旧值和新值仍处于现有限流高位阈值，视为上游把旧周期利用率与新 reset 拼在一起：保存新 reset，但 utilization 写 0。
5. `Allowed` rollover 样本已经明显下降时，说明上游给出了新周期实际值，直接采用。
6. `RejectedWindows` 中的窗口代表上游已明确拒绝请求，保留响应头中的高 utilization；同一 429 中未被拒绝的窗口仍按 `Allowed` rollover 规则处理。
7. 同一新 reset 的后续完整样本按正常更新处理，因此 rollover 保护不会永久锁死为 0。

该规则放在 AccountService 的纯合并 helper 中，并允许测试注入 `now`，避免依赖真实时钟。数据库写入仍通过现有 `AccountStore::update_usage`，不新增 schema。

## 主动 usage 边界

- `AccountService::refresh_usage` 保留，供后台 poller 和管理端手动刷新使用；获取结果后也经过统一跨周期合并，避免显式查询恰好撞上 rollover 时重新写回假高值。
- `UsagePollerService` 继续只选择 `auth_type=Oauth`、`status=Active`、`auto_poll_usage=true` 的账号。
- 删除 `refresh_usage_after_fable_request`、`reserve_opportunistic_usage_refresh`、`opportunistic_usage_refreshes`、`FABLE_USAGE_REFRESH_DELAY`、`FableUsageRefreshContext` 及 SlotGuardBody 中对应字段。
- Gateway 成功、流结束、非流缓存返回和 429 分支均不得隐式调用 `refresh_usage`。

## 429 与 Fable 模型级限流

- 429 的窗口头同时生成完整被动用量与拒绝窗口集合：完整用量用于持久化，拒绝集合决定哪些高位窗口可信；rate-limit 决策只接收真实拒绝窗口，避免其他 `status=allowed` 的跨周期残留高值造成错误隔离。
- 通用 5h/7d 明确耗尽时仍写账号级冷却。
- Fable 请求只有 `7d_oi` 拒绝/超阈值而通用窗口未耗尽时，继续返回 `RetryOtherAccount`，不写全局 `rate_limit_reset_at`。
- SetupToken 与 OAuth 都可持久化被动窗口；只有 OAuth 可以执行主动 usage 查询。

## 并发与失败处理

- Gateway 保持异步写入，不阻塞响应体转发；429 已经缓冲响应体，可在现有异步业务边界内完成持久化和分类。
- 合并操作沿用“读取账号后整体更新 usage_data”的现有模型，不引入新锁或迁移；每次合并必须保留该观察未包含的已有窗口和扩展字段。
- 被动写入失败只记录脱敏 debug/warn，不改变上游响应。
- 不记录完整响应头、token、邮箱或响应正文。

## 兼容性与回滚

- `/admin/accounts` 仍返回 `five_hour`、`seven_day`、`seven_day_sonnet`、`seven_day_fable` 等现有字段，不要求 ai-fund 或 cc2api web 改类型。
- 缺少 `7d_oi` 时保留已有 Fable 数据，不主动补查。
- 回滚只需恢复 Rust 代码和 spec；没有数据库迁移。
