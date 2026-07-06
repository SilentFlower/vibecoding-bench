# Brief — cc2api Haiku 半槽并发与展示

## Goal

- 让 cc2api 中真实 Haiku 请求按 0.5 个账号并发槽计入，同时保持后台“并发数”配置语义不变，并在账号管理页并发区域悬浮展示标准槽位、内部单位和排队信息。

## Scope

- 修改 `cc2api/src/service/account.rs` 的账号队列内部槽位单位：普通请求占 2 单位，Haiku 请求占 1 单位，账号 `concurrency` 仍表示普通请求容量。
- 修改 `cc2api/src/service/gateway.rs`，在真实上游转发路径进入账号槽位前按请求模型计算 `slot_units`，并保持本地拦截在 admission 前返回。
- 修改账号调度评分和管理 API 输出，按内部单位计算负载和满载，并返回前端展示所需的标准槽位、内部单位、活跃请求数和排队单位字段。
- 修改 `cc2api/web/src/api.ts` 和 `cc2api/web/src/components/Accounts.vue`，账号卡片并发区域展示标准槽位，并在鼠标悬浮时说明普通请求、Haiku 半槽、内部单位和排队信息。
- 补充后端并发队列、gateway admission、FIFO 公平、等待队列容量和缩容收敛相关测试。

## Non-Goals

- 不修改账号 `concurrency` 存储类型、表单提交语义或数据库 schema。
- 不改变 RPM admission 计数；RPM 仍按请求数计，不按半槽权重计。
- 不改变 `count_tokens` 当前是否消耗账号并发的既有行为。
- 不新增按模型自定义权重的 setting。
- 不修改 sub2api。
- 不改变等待队列容量语义；队列长度仍表示等待请求数。

## Key Context

- `cc2api/src/model/account.rs:171` 的 `Account.concurrency` 是整数配置，默认值 3，外部语义必须保持为普通请求容量。
- `cc2api/src/service/account.rs:155` 的 `AccountQueue` 当前用 Tokio `Semaphore` 控制账号槽位，`slots = concurrency`，`queue_cap = 2 × concurrency`。
- `cc2api/src/service/gateway.rs:432` 的 `GatewayService::acquire_account_admission` 必须保持“先账号槽位、后 RPM admission”的顺序。
- `cc2api/src/service/gateway.rs:1242` 附近的 warmup / Haiku probe 等本地拦截发生在账号槽位获取之前，命中拦截不应消耗账号槽位。
- 账号并发为 5 时内部容量为 10 单位；9 个 Haiku 占 9 单位后，新 Opus 需要 2 单位，必须等待。若 Opus 在队首，后续 Haiku 不得插队占用剩余 1 单位。
- 等待队列继续按请求数限制：账号并发为 5 时最多 10 个等待请求，不因 Haiku 半槽扩大到 20 个。
- 管理员缩小并发时不强杀已有请求；队列在请求释放后收敛到新内部容量。

## Acceptance

- 后台账号并发配置为 `N` 时，普通请求最多仍为 `N` 个并发；Haiku 请求最多可达到 `2N` 个并发；混合请求按 `普通 × 1 + Haiku × 0.5 <= N` 控制。
- 队首普通/Opus 请求需要 2 单位而剩余 1 单位时，后续 Haiku 不插队，保持 FIFO 公平。
- `GatewayService::acquire_account_admission` 仍保持先槽位后 RPM；槽位等待中、队列满、槽位超时都不得消耗 RPM。
- 账号调度评分和已满判断按内部单位计算。
- 管理 API 返回标准槽位值和内部单位值，前端账号卡片展示标准槽位，悬浮时解释当前活跃/排队情况和半槽规则。
- 本地拦截的 Haiku probe / warmup 仍不消耗账号槽位。
- 验证命令通过：`cd cc2api && cargo fmt --check && cargo test`，以及 `cd cc2api/web && npm run build`。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `python3 ./.trellis/scripts/task.py start .trellis/tasks/07-06-cc2api-haiku-half-concurrency`，再进入实现路由。
