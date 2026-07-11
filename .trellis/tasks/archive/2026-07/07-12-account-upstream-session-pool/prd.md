# 账号级上游 session 池

## Goal

在 `cc2api` 为每个账号增加可配置的上游 session 池，使多个下游真实 Claude Code session 可以同时进入 gateway，但发往 Anthropic 上游的 `metadata.user_id.session_id` 在一个活跃窗口内只暴露少量真实 session，从而避免同一账号在短时间出现过多不同上游 session。

该能力必须保留 gateway 内部真实 session 语义：账号 sticky、RPM 日志、排队和内部追踪仍使用下游真实 session；只在最终发往上游前改写 `metadata.user_id.session_id`。

## Confirmed Facts

- 现有 Claude Code session 识别来自 `metadata.user_id.session_id`，`generate_session_hash` 会在 Claude Code 模式直接返回该真实 session id：`cc2api/src/service/account.rs:1774`。
- RPM 日志中的 `session=` 取的是内部 `session_hash` 前 8 位：`cc2api/src/service/account.rs:1610`。
- 现有 `rewrite_metadata_user_id` 只替换 `device_id` 和 `account_uuid`，保留原始 `session_id`，因此上游会看到下游真实 session：`cc2api/src/service/rewriter.rs:1434`。
- `/v1/messages` 的 body 改写发生在 header 重写、CCH 和 `cc_version` 计算前，新增上游 session 改写必须进入这段最终 body 改写链路：`cc2api/src/service/rewriter.rs:1316`、`cc2api/src/service/gateway.rs:1463`。
- stateful message cache 的 key 由 `account.id` 和最终 body 中的 `metadata.user_id.session_id` 组成；上游 session 改写会影响该缓存会话边界：`cc2api/src/service/rewriter.rs:4157`。
- 新增账号字段必须同步 `model/account.rs`、`store/account_store.rs`、`handler/router.rs`、`web/src/api.ts` 和 `Accounts.vue`；SQLite/PostgreSQL schema 与迁移也必须同步。

## Requirements

- R1：账号级配置控制该能力，默认必须兼容旧行为。每个账号至少需要配置是否启用、上游 session 池容量、活跃 TTL、TTL 刷新策略。
- R1a：老账号迁移和新账号创建默认关闭该能力；推荐配置值用于 UI 预填和用户手动开启，但不自动改变老账号协议行为。
- R1b：上游 session 数量由账号级池容量控制，例如 `upstream_session_pool_size=3` 表示该账号在活跃 TTL 窗口内最多向上游暴露 3 个 distinct `metadata.user_id.session_id`。
- R1c：账号级池容量允许范围为 `1-20`，UI 推荐/预填值为 `3`。
- R1d：池容量配置为 `0` 时表示关闭 upstream session pool，等价于 `upstream_session_pool_enabled=false`；启用时有效容量必须在 `1-20` 范围内。
- R1e：账号级 TTL 允许范围为 `5-1440` 分钟，UI 推荐/预填值为 `60` 分钟。
- R2：上游 session 不能随机预生成；池内 upstream session 必须来自真实进入 gateway 的 Claude Code session id。
- R3：当真实 session 首次进入且账号的上游 session 池未满时，该真实 session 可以成为池内 upstream session，并记录活跃时间。
- R4：当池已满时，新的真实 session 仍允许进入 gateway，但发往上游时必须复用池内已有 upstream session，避免上游短时间看到更多 session。
- R4a：池满复用策略使用稳定哈希：同一个真实 session 在活跃池成员不变时必须稳定映射到同一个 upstream session，避免轮询导致单个真实 session 在请求间频繁切换上游 session。
- R5：真实 session 如果已经是池内 upstream session，且在 TTL 窗口内持续请求，应刷新该 upstream session 的活跃时间。
- R5a：TTL 刷新策略必须支持两种账号级表现形式：
  - `owner_only`：只有 upstream session 对应的真实 session 自己请求时才刷新 TTL；池满后的借用请求不刷新 TTL，利于池成员自然轮换。
  - `mapped_request`：任何被映射到该 upstream session 的请求都刷新 TTL，利于维持上游 session 和 stateful cache 稳定。
- R5b：账号级 TTL 刷新策略默认使用 `mapped_request`，降低 upstream session 轮换导致 stateful cache 会话边界变化的风险。
- R6：gateway 内部账号 sticky、RPM admission、队列和日志仍使用真实下游 session，不得用 upstream session 反向污染内部调度。
- R6a：本地 stateful message cache 必须继续按真实下游 session 隔离；上游 session 池只改变最终发往上游的 `metadata.user_id.session_id` 与对应 session header，不能让多个真实 session 共享同一个本地 stateful cache 状态。
- R7：主要对 Claude Code `/v1/messages` 生效；普通 API mimicry、`count_tokens`、bootstrap、usage poller 默认不受影响。
- R7a：必须处理遥测一致性。自动遥测生成的 message request/result event 必须使用最终上游 session id，不能使用真实下游 session id。
- R7b：Claude Code 客户端原生 event_logging / telemetry payload 中如包含 `session_id`、`parent_session_id` 或其他明确 session 字段，并且可提取真实 session id，则应通过同一账号 upstream session pool 映射后再发上游，避免遥测端重新暴露大量真实 session。
- R7c：遥测路径的 session 映射不得创建新的 upstream session 池成员；只能复用现有池成员。找不到映射或池为空时保持现有遥测改写行为并记录脱敏诊断，避免遥测请求反向改变主请求池状态。
- R8：日志只能输出短 session 标识、账号 id、池容量、动作和原因，不输出完整 `metadata.user_id` 或完整请求体。
- R9：Redis 与内存 cache 都要支持该池状态；并发请求下不能让同一账号瞬间超出配置的 upstream session 池容量。
- R10：TTL 到期清理采用请求路径懒清理。每次账号请求进入 upstream session pool 解析前，先清理该账号池内已过期成员；不新增后台清理任务。
- R11：管理端可展示当前 upstream session 池状态，例如活跃数量、容量、最早/最晚活跃时间；长时间无请求时存储中的过期残留允许存在，下一次请求会自动清理。

## Acceptance Criteria

- [ ] 管理端账号创建/编辑支持配置 upstream session pool 开关、容量、TTL 和 TTL 刷新策略，并能正确保存、读取和回显。
- [ ] 后端校验容量 `0` 或 `1-20`，TTL `5-1440`，刷新策略只能是 `mapped_request` 或 `owner_only`。
- [ ] 老账号迁移后默认保持旧行为；不启用该能力时，上游 `metadata.user_id.session_id` 与现有行为一致。
- [ ] 启用后，同一账号在同一 TTL 活跃窗口内发往上游的 distinct `session_id` 数不超过账号配置的池容量。
- [ ] 池内 upstream session 来源于真实下游 session，不是随机生成或按时间窗口合成的 session。
- [ ] 池内真实 session 持续请求时会刷新对应 upstream session 的活跃时间；超过 TTL 未刷新后可被新真实 session 替换。
- [ ] 每个账号可选择 `owner_only` 或 `mapped_request` TTL 刷新策略；两种策略都有单元测试覆盖。
- [ ] 池满时新真实 session 仍可请求，但最终 body 中 `metadata.user_id.session_id` 会映射为池内已有 upstream session。
- [ ] 自动遥测 request/result event 使用最终上游 session id；客户端 event_logging 中的 session 字段不会绕过 upstream session pool 暴露真实 session。
- [ ] TTL 过期成员在请求路径懒清理；不依赖后台任务即可释放过期槽位。
- [ ] 管理端能展示账号当前 upstream session 池活跃数量和容量。
- [ ] 内部 sticky 绑定和 RPM 日志仍以真实下游 session 为准，不因为上游 session 复用而把多个真实 session 合并成同一个内部 session。
- [ ] 覆盖账号字段迁移、handler 校验、store 读写、rewriter 改写、cache 池容量和前端构建的测试/验证。

## Out of Scope

- 不在本任务内修改 Anthropic 上游风控规则或做封号归因判定。
- 不在本任务内限制下游真实 session 进入 gateway 的数量。
- 不在本任务内改变账号并发槽位、RPM admission 或 Fable sticky fallback 的既有语义。
