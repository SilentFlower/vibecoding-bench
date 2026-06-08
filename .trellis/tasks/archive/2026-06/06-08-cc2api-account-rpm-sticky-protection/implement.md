# cc2api 账号级 RPM 粘性保护实施计划

## Implementation Checklist

- [x] 阅读 cc2api 账号模型、账号 store、cache store、gateway 账号选择和槽位获取链路。
- [x] 在账号模型和数据库初始化/迁移兼容逻辑中增加 RPM 配置字段，默认关闭。
- [x] 为 RedisStore / MemoryStore 增加账号分钟 RPM 计数或预占能力。
- [x] 在账号选择链路中区分粘性请求和非粘性请求。
- [x] 非粘性候选账号加入 RPM 可调度性过滤或评分降权。
- [x] 粘性账号 RPM 满时实现等待/拒绝，不因 RPM 直接切号。
- [x] 确保 RPM 等待不长期占用并发槽位；优先在拿槽位前完成 RPM admission。
- [x] 增加可读 RPM 日志，输出账号、当前值、限制、粘性状态和动作。
- [x] 更新管理 API 或账号 DTO，返回 RPM 配置和当前分钟状态。
- [x] 更新 Vue 账号页面，支持编辑 RPM 上限，并展示当前分钟 `已用 / 总量`、剩余或已满状态。
- [x] 增加单元测试覆盖关闭 RPM、非粘性跳过、粘性不切号、单账号超限行为。

## Implementation Notes

- 粘性绑定采用延迟提交：`select_account_with_context` 只返回候选账号和粘性状态；Gateway 在 RPM admission、并发槽位、请求改写和上游 token 解析均成功后，再调用 `bind_selected_session` 提交新会话绑定。
- 延迟提交用于避免 RPM 满、排队失败或 token 失败时把 session 绑定到未实际承载请求的账号，导致后续请求误判为粘性请求并破坏换号削峰。
- `select_account` 保留旧兼容语义，直接调用时仍会提交粘性绑定；Gateway 使用 `select_account_with_context` 走延迟绑定。
- 粘性请求 RPM 超限默认最多等待 5 秒，超过后返回本地 429；非粘性请求 RPM 超限会排除当前账号并重新选号。
- Check-all 过程中修正了自动遥测激活顺序：`/v1/messages` 的遥测会话会等 RPM admission、并发槽位、请求改写和上游 token 解析成功后再激活，避免被 RPM 跳过的账号产生额外上游副作用。

## Validation

- [x] 在 `/root/project/cc2api` 执行 `cargo test --test account_scheduler_test -- --nocapture`。
- [x] 在 `/root/project/cc2api` 执行 `cargo test --test gateway_429_retry_test -- --nocapture`。
- [x] 在 `/root/project/cc2api` 执行 `cargo test -q --no-run`。
- [x] 在 `/root/project/cc2api` 执行完整 `cargo test -- --nocapture`。
- [x] 在 `/root/project/cc2api/web` 执行 `npm run build`。
- [ ] `cargo fmt --check` 当前会要求格式化多个既有文件，未全仓格式化以避免扩大本任务 diff；本任务不混入全仓格式化，后续可单独做格式化提交。

## Review Gates

- 开始实现前确认 task status 已进入 `in_progress`。
- 实现前先过 `trellis-route(implement)`。
- 完成后走 `trellis-route(check)`，至少执行目标测试和一次代码审查。
