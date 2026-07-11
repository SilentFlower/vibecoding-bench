# 账号级上游 session 池设计

## 目标边界

本任务只限制发往上游的 Claude Code `session_id` 数量，不限制下游真实 session 进入 gateway 的数量。内部 sticky、RPM、账号排队和日志仍使用真实下游 session；上游 session 池只影响最终 `/v1/messages` body 与对应 session header。

## 账号配置

新增账号级字段：

- `upstream_session_pool_enabled: bool`，默认 `false`。
- `upstream_session_pool_size: i32`，默认 `3`，有效范围 `1-20`；值为 `0` 时等价关闭。
- `upstream_session_ttl_minutes: i32`，默认 `60`，有效范围 `5-1440`。
- `upstream_session_refresh_policy: string`，默认 `mapped_request`，可选 `mapped_request` / `owner_only`。

字段同步范围：

- Rust model：`cc2api/src/model/account.rs`
- store 映射：`cc2api/src/store/account_store.rs`
- SQLite / PostgreSQL schema 与迁移：`cc2api/src/store/db.rs`
- 管理 API create/update/list：`cc2api/src/handler/router.rs`
- 前端类型与账号表单：`cc2api/web/src/api.ts`、`cc2api/web/src/components/Accounts.vue`

## 池状态模型

池成员必须来自真实下游 Claude Code session，不预生成随机 ID。

每个账号维护一组活跃 upstream session 成员：

```text
key = upstream_session_pool:{account_id}
member = real_session_id
score/value = last_seen_timestamp_millis
```

成员自身就是发给上游的 `session_id`。这保证池内 upstream session 都来自真实请求。

## 解析算法

输入：

- `account_id`
- `real_session_id`
- `pool_size`
- `ttl_minutes`
- `refresh_policy`

流程：

1. 如果功能关闭、容量为 `0`、不是 Claude Code `/v1/messages` 或无法提取真实 session，则不改写上游 session。
2. 对账号池执行懒清理：删除 `last_seen + ttl < now` 的成员。
3. 如果 `real_session_id` 已在池内：
   - 刷新该成员 `last_seen`。
   - 返回 `upstream_session_id = real_session_id`。
4. 如果池未满：
   - 插入 `real_session_id` 并记录 `last_seen = now`。
   - 返回 `upstream_session_id = real_session_id`。
5. 如果池已满：
   - 取当前成员列表，按 member 字符串排序，保证映射稳定。
   - 使用 `hash(real_session_id) % active_count` 选择一个已有成员。
   - `mapped_request`：刷新被选择成员的 `last_seen`。
   - `owner_only`：不刷新被选择成员。
   - 返回被选择成员作为 `upstream_session_id`。

Redis 实现必须保证“懒清理 + 是否已存在 + 容量判断 + 插入/选择/刷新”是原子的，优先使用 Lua 脚本。内存实现用单个 mutex 覆盖该账号池更新。

## Gateway 与 Rewriter 数据流

1. `GatewayService::handle_request_inner` 继续先用真实 `session_hash` 做账号选择、sticky 和 RPM。
2. 拿到账号并通过 admission 后，在 body rewrite 前根据账号配置解析 upstream session。
3. 将可选 `UpstreamSessionOverride` 传入 rewriter：

```text
real_session_id
upstream_session_id
action = owner_hit | admitted | mapped | disabled
```

4. `rewrite_metadata_user_id` 在 Claude Code 模式下仍改写 `device_id` / `account_uuid`，并在 override 存在时把 JSON 或 legacy 格式中的 `session_id` 替换为 `upstream_session_id`。
5. header 重写继续基于 `rewritten_body_map` 生成 `X-Claude-Code-Session-Id`，从而自动与 body 中的 upstream session 对齐。
6. 日志输出短 session 标识、账号 id、池容量和动作，不输出完整 `metadata.user_id` 或完整请求体。

## 遥测一致性

上游 session 池启用后，遥测不能重新暴露真实下游 session。

- 自动遥测 `MessageTelemetryContext` 必须从最终 `rewritten_body` 读取 session。当前 `build_message_telemetry_context` 已按 `rewritten_body` 提取 session，接入时需要保留该顺序：先改写 upstream session，再构造 telemetry context。
- 自动遥测 request/result event 中的 `session_id` 应为 upstream session id；真实下游 session 只允许用于 gateway 内部 sticky、RPM、stateful cache key 和脱敏日志。
- 客户端原生 event_logging / telemetry payload 中如果存在 `session_id`、`parent_session_id` 等明确 session 字段，rewriter 应尝试用同一账号 upstream session pool 映射后再发送给上游。
- 遥测路径只能复用已有池成员，不应因为 telemetry payload 里的 session 字段创建新的 upstream session 成员；否则没有主请求的 telemetry 可能扩大上游 session 数。
- 如果 telemetry session 映射失败、池为空或字段格式无法识别，保持现有遥测改写行为并输出脱敏诊断，不阻断遥测请求。
- 测试必须覆盖：主请求 upstream session 改写后自动遥测 session 与 body/header 一致；event_logging 中的 session 字段被映射或在无法映射时失败开放。

## Stateful Cache 隔离

当前 `stateful_session_key` 使用最终 body 中的 `metadata.user_id.session_id`。引入 upstream session 池后，必须避免多个真实 session 因共享 upstream session 而共享本地 stateful cache。

设计要求：

- rewriter 在计算本地 stateful cache key 时优先使用 override 中的 `real_session_id`。
- 只有发给上游的 body/header 使用 `upstream_session_id`。
- 这样即使多个真实 session 映射到同一个 upstream session，本地 cache anchor 仍按真实 session 隔离，避免跨会话污染。

## 管理端展示

账号列表或详情可展示：

- upstream session pool 开关、容量、TTL、刷新策略。
- 当前活跃 upstream session 数。
- 最早/最晚活跃时间。

过期成员允许在无请求时暂时留在存储中；管理端展示可以读取时执行同样的懒清理，也可以标注为“当前缓存状态”。

## 兼容与回滚

- 默认关闭，老账号升级后行为不变。
- 禁用或容量设为 `0` 后，请求恢复现有行为：上游收到真实下游 session。
- 不修改账号 sticky 绑定、不修改 RPM 计数语义、不改变 Fable sticky fallback。
- 如果 Redis 池解析失败，推荐失败开放：记录 warn，保持原始真实 session 发上游，避免请求失败。

## 测试重点

- disabled / size=0 不改写。
- 池未满时真实 session 成为 upstream session。
- 池满时 distinct upstream session 不超过容量。
- 稳定哈希在成员不变时保持同一真实 session 映射稳定。
- `mapped_request` 会刷新被借用成员 TTL，`owner_only` 不刷新。
- TTL 懒清理后新 session 能占用释放出的槽位。
- body 中 `metadata.user_id.session_id` 和 `X-Claude-Code-Session-Id` 对齐。
- 自动遥测和 event_logging 不泄露未映射的真实 session。
- 本地 stateful cache key 仍按真实 session 隔离。
