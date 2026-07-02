# 修正 cc2api 排队请求提前消耗 RPM

## Goal

修正 cc2api gateway 的账号 RPM 计数时机，确保只有真正获得账号并发槽位、即将发往上游的请求才消耗 RPM。

## Background

- 用户反馈：当账号并发为 4、等待队列上限为 8 时，新进来的请求如果只是排队等待，也会让 RPM `+1`，这不符合预期。
- 当前代码证据：
  - `cc2api/src/service/gateway.rs:1238` 在获取并发槽位前调用 `acquire_account_rpm`。
  - `cc2api/src/service/gateway.rs:1253` 之后才进入账号级 FIFO 并发队列。
  - `cc2api/src/service/account.rs:746` 的 `acquire_account_rpm` 语义是“在发往上游前预占账号 RPM”。
  - `cc2api/src/store/memory.rs:121` 和 `cc2api/src/store/redis.rs:127` 的 `try_acquire_account_rpm` 会在获取成功时递增 RPM 计数；Redis 超限路径会回滚超额递增，但已获取成功的排队请求不会回滚。
- 期望语义：RPM 表示账号在当前分钟窗口内实际开始上游转发的请求数，而不是进入等待队列或尝试排队的请求数。

## Requirements

- R1：gateway 必须先获得账号并发槽位，再进行该账号 RPM admission。
- R2：请求处于账号并发等待队列期间，不得递增该账号 RPM。
- R3：请求因队列满、槽位等待超时、队列关闭或换号重试而没有获得该账号槽位时，不得消耗该账号 RPM。
- R4：保留现有粘性会话语义：粘性账号 RPM 饱和时不能随意切换账号；非粘性请求 RPM 饱和时仍可换号。
- R5：保留现有自动遥测本地假响应、瞬时 429 软退避、并发槽位释放守卫和上游 429 重试行为。
- R6：补充覆盖 RPM 与并发队列交互的后端测试，明确等待中请求不会提前消耗 RPM。

## Acceptance Criteria

- [ ] 并发槽位被占满时，另一个请求在 `queue.acquire(...)` 等待期间，`get_account_rpm_status` 的 `current` 不会因为该等待请求增加。
- [ ] 等待请求获得槽位并通过 RPM admission 后，RPM 才增加。
- [ ] 队列满或槽位等待超时路径不会消耗 RPM；如实现范围内已有相近测试，应扩展而不是重复造大 fixture。
- [ ] 非粘性 RPM 饱和换号、粘性 RPM 饱和等待/拒绝的既有行为保持通过。
- [ ] `cd cc2api && cargo fmt --check` 通过。
- [ ] `cd cc2api && cargo test` 通过；若环境限制无法全量完成，至少运行相关定向测试并说明原因。

## Out of Scope

- 不新增管理端配置项或前端展示。
- 不改变 `rpm_limit` 字段含义、数据库迁移或管理 API 结构。
- 不重写账号选择评分、队列容量公式或 Redis RPM 存储模型。

## Implementation Notes

- 这是轻量缺陷修复，PRD-only 足够；实现时仍必须按 cc2api 后端规范读取相关 spec。
- 主要风险是移动 RPM admission 后，错误路径必须继续释放并发槽位，且非粘性请求在 RPM 饱和后换号时不能泄漏当前账号槽位。
- 优先复用现有 `AccountQueue`、`SlotReleaseGuard` 和 `acquire_account_rpm`，避免引入新的跨模块状态。
