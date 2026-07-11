# Brief — 账号级上游 session 池

## Goal

- 在 `cc2api` 为每个账号增加默认关闭的上游 session 池，让多个下游真实 Claude Code session 可以进入 gateway，但同一账号在活跃窗口内只向上游暴露受控数量的 `metadata.user_id.session_id`。

## Scope

- 新增账号级配置：`upstream_session_pool_enabled`、`upstream_session_pool_size`、`upstream_session_ttl_minutes`、`upstream_session_refresh_policy`。
- 容量范围为 `1-20`，UI 推荐值 `3`；容量 `0` 表示关闭。
- TTL 范围为 `5-1440` 分钟，UI 推荐值 `60`。
- 刷新策略支持 `mapped_request` 和 `owner_only`，默认 `mapped_request`。
- 池成员必须来自真实下游 Claude Code session，不能随机预生成或按时间窗口合成。
- 池满后使用稳定哈希把新的真实 session 映射到已有 upstream session。
- TTL 过期成员在请求路径懒清理，不新增后台清理任务。
- 同步 Rust model、store、SQLite/PostgreSQL schema 与迁移、handler、前端 `api.ts` 和 `Accounts.vue`。
- 确保自动遥测和客户端 event_logging 的 session 字段与最终 upstream session 对齐，不绕过池暴露真实 session。

## Non-Goals

- 不限制下游真实 session 进入 gateway 的数量。
- 不修改 Anthropic 上游风控规则或做封号归因判定。
- 不改变账号 sticky、RPM admission、账号并发槽位或 Fable sticky fallback 语义。
- 不让多个真实 session 共享同一个本地 stateful cache 状态。
- 不让遥测路径创建新的 upstream session 池成员。

## Key Context

- Claude Code 内部 session 识别来自 `metadata.user_id.session_id`，`generate_session_hash` 在 Claude Code 模式直接返回真实 session：`cc2api/src/service/account.rs:1774`。
- 当前 `rewrite_metadata_user_id` 只替换 `device_id` / `account_uuid`，保留真实 `session_id`：`cc2api/src/service/rewriter.rs:1434`。
- `/v1/messages` body 改写发生在 header 重写、CCH 和 `cc_version` 计算前：`cc2api/src/service/rewriter.rs:1316`、`cc2api/src/service/gateway.rs:1463`。
- `X-Claude-Code-Session-Id` 从改写后的 body 提取 session，因此 body session 改写后 header 应自动对齐。
- 当前 stateful message cache key 由 `account.id` 和最终 body 中的 `metadata.user_id.session_id` 组成：`cc2api/src/service/rewriter.rs:4157`。实现时必须让本地 stateful cache key 优先使用真实下游 session，只让发给上游的 body/header 使用 upstream session。
- 自动遥测 context 当前从 `rewritten_body` 提取 session；实现时必须保持先改写 upstream session、再构造 telemetry context。
- 客户端 event_logging 中的 `session_id` / `parent_session_id` 等字段也需要映射；无法映射时失败开放并输出脱敏诊断。
- Redis 池解析必须原子化，避免并发新 session 同时入池超过容量；内存实现用 mutex 保持等价语义。
- 默认关闭，老账号迁移后行为必须不变；禁用或容量为 `0` 时恢复旧行为。
- Redis 池解析异常应失败开放：记录 warning，保留真实 session 发上游，避免请求中断。

## Acceptance

- 管理端账号创建/编辑支持配置开关、容量、TTL 和刷新策略，并能保存、读取、回显。
- 后端校验容量 `0` 或 `1-20`，TTL `5-1440`，刷新策略只能是 `mapped_request` 或 `owner_only`。
- 不启用时，上游 `metadata.user_id.session_id` 与现有行为一致。
- 启用后，同一账号在同一 TTL 活跃窗口内发往上游的 distinct `session_id` 数不超过账号配置容量。
- 池内 upstream session 来源于真实下游 session。
- 池内真实 session 持续请求时刷新活跃时间；超过 TTL 未刷新后可被新真实 session 替换。
- `mapped_request` 与 `owner_only` 两种刷新策略都有测试覆盖。
- 池满时新真实 session 仍可请求，最终 body 映射为池内已有 upstream session。
- TTL 过期成员在请求路径懒清理，不依赖后台任务释放槽位。
- 管理端能展示当前 upstream session 池活跃数量和容量。
- 内部 sticky 绑定、RPM 日志和本地 stateful cache 仍以真实下游 session 为准。
- 自动遥测 request/result event 使用最终 upstream session，客户端 event_logging 不绕过池暴露真实 session。
- 覆盖账号字段迁移、handler 校验、store 读写、rewriter 改写、cache 池容量和前端构建验证。

## Next Step

- 用户确认 brief 后运行 `python3 ./.trellis/scripts/task.py start .trellis/tasks/07-12-account-upstream-session-pool`，进入实现阶段；随后按 Trellis route gate 进入 `trellis-route(implement)`。
