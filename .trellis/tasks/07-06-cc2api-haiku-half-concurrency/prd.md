# cc2api Haiku 半槽并发与展示

## Goal

让 cc2api 中真实 Haiku 请求按 0.5 个账号并发槽计入，同时保持后台“并发数”配置语义不变，并在账号管理页并发区域悬浮展示标准槽位、内部单位和排队信息。

## Background

- `cc2api/src/model/account.rs:171` 的 `Account.concurrency` 是整数配置，默认值为 3，当前语义是账号允许的普通请求并发数。
- `cc2api/src/service/account.rs:155` 的 `AccountQueue` 使用 Tokio `Semaphore` 控制账号槽位，当前 `slots` 容量等于 `concurrency`，`queue_cap` 容量等于 `2 × concurrency`。
- `cc2api/src/service/gateway.rs:432` 的 `GatewayService::acquire_account_admission` 先获取账号槽位，再调用 RPM admission；该顺序由 `.trellis/spec/cc2api/backend/service-architecture.md` 明确约束。
- `cc2api/src/service/gateway.rs:1242` 的 warmup / Haiku probe 等本地拦截发生在账号槽位获取之前，命中拦截的请求不应进入账号并发计量。
- `cc2api/src/service/account.rs:1217` 的账号调度评分会使用当前活跃并发和排队数量计算负载，并优先排除已满账号。
- `cc2api/src/handler/router.rs:247` 通过管理 API 返回 `current_concurrency` / `queued_requests`，`cc2api/web/src/components/Accounts.vue:721` 在账号卡片显示当前并发。

## Requirements

- R1：后台账号“并发数”配置继续表示普通请求容量。管理员仍填写 `3` 表示最多 3 个普通请求；不能要求管理员手动填成 6。
- R2：账号槽位内部采用整数单位计量，推荐比例为 `1 标准并发槽 = 2 内部单位`。普通请求占 2 单位，Haiku 请求占 1 单位。
- R3：Haiku 请求判定以即将进入上游转发路径的请求模型 ID 为准；所有模型 ID 小写后包含 `haiku` 的请求都按 0.5 标准槽计量，不只硬编码 `claude-haiku-4-5`。当前 cc2api 没有 sub2api 那种跨平台模型映射，因此不需要处理“请求名是 Haiku、实际映射到 Sonnet”的场景。
- R4：仅真实进入上游转发链路的请求消耗账号槽位。warmup、suggestion、Auto Mode classifier、Haiku probe、assistant prefill、telemetry 本地假响应等既有本地拦截路径不得因为本改动新增账号槽位消耗。
- R5：账号调度的“已满”判断和负载评分必须使用内部单位，避免 Haiku 半槽请求被按完整请求计入或被完全忽略。
- R6：管理端账号卡片仍用标准槽位展示当前并发，例如 `1.5/3`；鼠标悬浮在并发区域时显示更具体的解释，包括普通请求=1、Haiku=0.5、当前标准槽位、内部单位、活跃请求数和排队信息。
- R7：管理 API 应提供前端展示所需的结构化字段，避免前端根据后端内部实现猜测单位。
- R8：本任务不新增数据库字段、不做迁移、不新增可配置 setting；Haiku 权重固定为 0.5，普通请求固定为 1.0。
- R9：账号队列应优先保持 FIFO 公平性。若剩余容量不足以满足队首请求，即使后续半槽 Haiku 可以利用剩余单位，也不应绕过队首普通/Opus 请求。
- R10：等待队列容量继续按请求数计量，保持 `2 × concurrency` 个等待请求，不因 Haiku 半槽而扩大为 `4 × concurrency`。
- R11：管理员缩小账号并发时不强制终止已有请求；内部容量应沿用现有收敛语义，在请求自然结束后逐步符合新容量。
- R12：账号切换策略沿用现有逻辑。若某账号容量不足、队列满或等待超时，网关继续按已有机制排除该账号并尝试其他可用账号。
- R13：前端默认展示标准槽位，不直接暴露内部单位作为主文案，避免误导管理员把 `concurrency` 手动填成 2 倍。

## Non-Goals

- 不修改账号 `concurrency` 存储类型或管理表单提交语义。
- 不改变 RPM admission 计数；RPM 仍按即将发往上游的请求数计数，不按半槽权重计数。
- 不改变 `count_tokens` 当前是否消耗账号并发的既有行为。
- 不引入按模型自定义权重的设置页。
- 不修改 sub2api。
- 不改变等待队列容量的含义；队列长度仍表示等待请求数。

## Acceptance Criteria

- [ ] 后台账号并发配置为 `N` 时，普通请求最多仍为 `N` 个并发；Haiku 请求最多可达到 `2N` 个并发；普通与 Haiku 混合时按 `普通 × 1 + Haiku × 0.5 <= N` 控制。
- [ ] 当账号并发为 5 且已有 9 个 Haiku 活跃时，剩余 0.5 标准槽不足以接纳 Opus/普通请求；新 Opus 请求进入等待队列，直到至少再释放 0.5 标准槽。若该 Opus 已在队首等待，后续 Haiku 不应插队占用剩余半槽。
- [ ] `GatewayService::acquire_account_admission` 仍保持“先账号槽位、后 RPM admission”的顺序；槽位等待中、队列满、槽位超时都不得消耗 RPM。
- [ ] 等待队列容量仍按请求数限制：账号并发为 5 时，最多允许 10 个等待请求，不按 Haiku 权重扩大。
- [ ] 管理员缩小并发时已有请求不被中断，账号队列在请求释放后收敛到新内部容量。
- [ ] 账号调度评分和已满判断按内部单位计算；半槽 Haiku 不应让账号过早被视为满，也不应在容量不足时绕过等待队列。
- [ ] 管理 API 返回标准槽位值和内部单位值，前端账号卡片并发区域展示标准槽位，并在悬浮时解释当前活跃/排队情况。
- [ ] 本地拦截的 Haiku probe / warmup 仍不消耗账号槽位。
- [ ] 覆盖后端并发队列和 gateway admission 的定向测试，并运行 `cd cc2api && cargo fmt --check && cargo test`。
- [ ] 前端类型和账号卡片展示同步更新，并运行 `cd cc2api/web && npm run build`。

## Technical Notes

- 该任务跨 `cc2api/src/service/account.rs`、`cc2api/src/service/gateway.rs`、`cc2api/src/handler/router.rs`、`cc2api/web/src/api.ts` 和 `cc2api/web/src/components/Accounts.vue`。
- `tokio::sync::Semaphore` 支持一次获取多个 permit，可用于普通请求占 2 单位、Haiku 请求占 1 单位；返回的 `OwnedSemaphorePermit` 生命周期仍可由现有 `SlotReleaseGuard` / `SlotGuardBody` 承接。
