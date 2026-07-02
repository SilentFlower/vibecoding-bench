# Brief — 修正 cc2api 排队请求提前消耗 RPM

## Goal

- 修正 cc2api gateway 的账号 RPM 计数时机，确保只有真正获得账号并发槽位、即将发往上游的请求才消耗 RPM。

## Scope

- 调整 gateway 热路径中账号并发槽位获取与 RPM admission 的顺序。
- 确保排队中、队列满、槽位等待超时或换号前未获得槽位的请求不消耗该账号 RPM。
- 补充后端测试覆盖 RPM 与账号并发队列交互，尤其是等待中请求不提前增加 RPM。

## Non-Goals

- 不新增管理端配置项或前端展示。
- 不改变 `rpm_limit` 字段含义、数据库迁移或管理 API 结构。
- 不重写账号选择评分、队列容量公式或 Redis RPM 存储模型。

## Key Context

- 现有证据：`cc2api/src/service/gateway.rs:1238` 在获取并发槽位前调用 `acquire_account_rpm`，`cc2api/src/service/gateway.rs:1253` 之后才进入账号级 FIFO 并发队列。
- RPM admission 入口：`cc2api/src/service/account.rs:746`。
- RPM 存储递增：`cc2api/src/store/memory.rs:121`、`cc2api/src/store/redis.rs:127`。
- 相关测试：`cc2api/tests/account_scheduler_test.rs`、`cc2api/tests/gateway_429_retry_test.rs`。
- 风险：移动 RPM admission 后，非粘性 RPM 饱和换号路径必须释放当前账号并发槽位；粘性账号 RPM 饱和时仍不能随意切换账号。

## Acceptance

- 并发槽位被占满时，另一个请求在 `queue.acquire(...)` 等待期间，`get_account_rpm_status` 的 `current` 不会因为该等待请求增加。
- 等待请求获得槽位并通过 RPM admission 后，RPM 才增加。
- 队列满或槽位等待超时路径不会消耗 RPM。
- 非粘性 RPM 饱和换号、粘性 RPM 饱和等待/拒绝的既有行为保持通过。
- `cd cc2api && cargo fmt --check` 与 `cd cc2api && cargo test` 通过；如环境限制无法全量完成，说明原因并至少运行相关定向测试。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `task.py start`，进入 `trellis-route(implement)`。
