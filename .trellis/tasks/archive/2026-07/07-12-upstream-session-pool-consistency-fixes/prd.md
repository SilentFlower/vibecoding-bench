# 修复上游 session 池一致性问题

## Goal

修复账号级上游 session 池在 header/body 对齐、容量动态缩小、真实 session 稳定映射和遥测复用上的一致性问题，确保同一次请求及其关联遥测使用同一个实际 upstream session，同时继续限制账号活跃 upstream session 数量。

## Background

- Claude Code `/v1/messages` body 已能把 `metadata.user_id.session_id` 改写为 upstream session，但 Claude Code header 分支仍可能透传真实 `X-Claude-Code-Session-Id`，导致 header/body 不一致。
- 对本地 `data/flows` 的 235 条 `/v1/messages?beta=true` 抓包进行脱敏核对后，222 条正常请求全部 header/body session 一致；13 条 `max_tokens=1` warmup probe 中有 1 条不一致。因此本次只修复 session 池实际改变 body session 时产生的不一致，不把所有 `/v1/messages` 强制规范化。
- Redis 和 MemoryStore 只按 TTL 清理成员；账号容量从较大值调小时，活跃成员数可能长期超过新容量。
- 当前池满映射只按“当前活跃成员排序后取模”计算，没有保存 `real_session_id -> upstream_session_id` 关系。成员集合变化后，同一真实 session 可能切换 upstream session；延迟到达的 `event_logging` 也只能按当前成员重新计算，不能保证对应主请求实际使用的 upstream session。
- 自动 message request/result 遥测已经从最终 rewritten body 获取 session，此顺序必须保留。

## Requirements

### R1：Header 与 Body 使用同一 upstream session

- Claude Code `/v1/messages` 只有在 session 池解析结果满足 `real_session_id != upstream_session_id`、即 body session 确实被改写时，最终 `X-Claude-Code-Session-Id` 才必须用 upstream session 覆盖客户端传入值。
- 池未改变 body session 的 admitted/owner-hit 请求和未进入池解析的 warmup probe 保持现有 header 行为，避免抹平抓包中存在的官方特殊路径。
- 功能关闭、容量为 `0` 或池解析失败开放时，header/body 都继续使用真实下游 session。
- header 覆盖必须发生在最终上游转发前，并保持现有 CCH、`cc_version`、beta 和其他 header 画像行为不变。

### R2：容量缩小后原子收敛

- Redis 和 MemoryStore 在每次 resolve/status 读取时，都必须把活跃成员数收敛到当前账号容量以内。
- 容量缩小时按 `last_seen` 从旧到新淘汰，时间相同时按 session id 稳定排序，优先保留最近仍承载请求的 upstream session。
- 收敛、TTL 清理、成员解析、映射更新必须处于同一原子临界区；Redis 使用 Lua，MemoryStore 使用 mutex。
- 被淘汰成员关联的真实 session 映射必须立即逻辑失效，不能继续返回已不在池内的 upstream session；物理记录允许按访问或 TTL 懒清理，避免热路径全量扫描。
- 功能关闭或容量为 `0` 时不要求立即执行远程清理，但重新启用后的第一次 resolve/status 必须按当前容量和 TTL 收敛。

### R3：保存并复用真实到上游映射

- 主请求解析成功后保存 `real_session_id -> upstream_session_id` 映射。
- 只要映射目标仍是活跃池成员，同一真实 session 的后续主请求必须继续复用该 upstream session，不因其他成员加入、过期或排序变化而切换。
- 映射目标过期或被容量收敛淘汰后，旧映射必须失效；下一次主请求才允许重新接纳或重新映射。
- `mapped_request` 继续刷新被借用 upstream session 的活跃时间；`owner_only` 只刷新成员自身请求。
- 映射状态不得改变 sticky、RPM、账号队列和本地 stateful cache 仍使用真实 session 的现有契约。

### R4：遥测使用主请求实际 upstream session

- 自动 message request/result 遥测继续从 rewritten body 获取最终 upstream session。
- 客户端 `event_logging` 只读查询已保存的真实到上游映射，`allow_insert=false`，不得创建池成员、不得刷新成员 TTL。
- `event_logging` 只有在映射目标仍为活跃成员时才改写 session 字段；映射缺失、目标失效或 cache 异常时失败开放并记录脱敏诊断。
- 启动类账号遥测没有对应主请求，继续使用独立 telemetry run session，不纳入本次映射约束。

### R5：兼容与隐私

- 上游 session 池仍默认关闭；默认容量 `3`、TTL `60` 分钟、策略 `mapped_request` 不变。
- 不新增完整 session、metadata、header 或请求体日志；诊断只允许账号 ID、动作、原因和短 hash。
- Redis/cache 异常继续失败开放，不能阻断正常请求。

## Acceptance Criteria

- [ ] Claude Code 主请求携带真实 session header，且池把 body 映射到不同 upstream session 后，最终 header/body session 完全一致。
- [ ] 未发生 body session 改写时不额外覆盖 header，warmup probe 路径保持现有行为。
- [ ] 功能关闭和 Redis/cache 失败开放时，最终 header/body 都使用真实 session。
- [ ] 池容量从 `5` 调为 `2` 后，下一次 resolve/status 返回的活跃成员数不超过 `2`，Redis 与 MemoryStore 行为一致。
- [ ] 容量淘汰后，所有指向被淘汰成员的映射均失效。
- [ ] 活跃成员集合发生增删时，只要原映射目标仍活跃，同一真实 session 的 upstream session 保持不变。
- [ ] 原映射目标过期后，主请求可以重新映射；只读遥测不能复活目标或创建新成员。
- [ ] `event_logging` 使用该真实 session 最近一次有效主请求保存的 upstream session，而不是按当前成员集合重新取模。
- [ ] `mapped_request` / `owner_only` 刷新语义保持不变，并覆盖 Redis Lua 人工审查与 MemoryStore 单测。
- [ ] sticky、RPM、队列和 stateful cache key 仍使用真实 session。
- [ ] `cargo fmt --check`、`cargo test`、`cargo test cch` 和 `web npm run build` 全部通过。

## Out Of Scope

- 不修改账号级配置字段、默认值或管理端交互形式。
- 不改变自动 telemetry 启动事件和 GrowthBook run session 的生成方式。
- 不限制下游真实 session 并发进入 gateway。
