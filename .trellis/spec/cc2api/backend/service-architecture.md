# cc2api Backend Service Architecture

## 适用范围

本文件约束 `cc2api/src/` 的 Rust 后端结构：

```text
src/main.rs
src/handler/
src/middleware/
src/model/
src/service/
src/store/
src/tlsfp/
```

## 分层契约

- `main.rs` 只负责装配：加载 `Config`、初始化 tracing、注册 SQLx Any driver、初始化 DB/cache/store/service、启动后台 poller、构建 router。
- `handler/router.rs` 负责 HTTP 路由、DTO 解析、管理 API 返回形状和静态资源 fallback，不把复杂业务逻辑塞进 handler。
- `middleware/auth.rs` 只处理管理端 Bearer 密码认证；网关 API token 鉴权留在 `gateway_fallback` 进入 `TokenStore` 查询。
- `model/` 是 DB/API 共享结构。新增字段要同步 store 映射、前端类型和迁移。
- `service/` 放业务逻辑：账号调度、Gateway 转发、OAuth、usage poller、telemetry、rewriter、version profile。
- `store/` 放持久化与缓存抽象。不要让 handler 直接写 SQL。
- `tlsfp/` 和 `craftls/` 是 TLS 指纹链路，改动要按协议/抓包任务处理。

## Gateway 热路径规则

`GatewayService::handle_request` / `handle_request_inner` 是最高风险路径。修改前必须明确：

- 请求是否应在账号选择前拦截，例如 assistant prefill、warmup、Auto Mode classifier、非流探针缓存。
- 请求是否会消耗账号并发/RPM；粘性会话下不能因为 RPM 超限随意切号破坏缓存。
- 请求体是否被读取、解压、改写或缓存；读取后转发必须使用最终 body。
- Claude Code 请求改写必须在 CCH 和 `cc_version` 重新计算前完成。
- 上游非成功响应如果要重试，必须保留原有错误体兼容性和敏感信息边界。
- SSE 流式响应只能插入明确允许的 keepalive/comment，不要重排上游 chunk。

## Scenario: 账号级上游 session 池

### 1. Scope / Trigger

- Trigger：修改账号级 upstream session pool、Claude Code `/v1/messages` session 改写、event_logging 遥测 session、stateful message cache、Redis/Memory cache 状态或 Accounts 管理 UI 时适用。
- 目标：允许多个真实下游 Claude Code session 同时进入 gateway，但限制同一账号在一个活跃 TTL 窗口内发往上游的 distinct `metadata.user_id.session_id` 数量。

### 2. Signatures

- 账号字段：`Account.upstream_session_pool_enabled: bool`、`upstream_session_pool_size: i32`、`upstream_session_ttl_minutes: i32`、`upstream_session_refresh_policy: String`。
- 账号默认值：默认关闭；推荐容量 `3`；默认 TTL `60` 分钟；默认策略 `mapped_request`。
- 校验范围：容量允许 `0` 或 `1..=20`，`0` 等价关闭；TTL 允许 `5..=1440`；策略只允许 `mapped_request` / `owner_only`。
- cache 入口：`CacheStore::resolve_upstream_session_pool(account_id, real_session_id, pool_size, ttl, refresh_policy, allow_insert).await -> Result<UpstreamSessionPoolResolve, AppError>`。
- 状态入口：`CacheStore::get_upstream_session_pool_status(account_id, pool_size, ttl).await -> Result<UpstreamSessionPoolStatus, AppError>`。
- Gateway 入口：`GatewayService::build_upstream_session_rewrite(account, path, body_map, client_type).await -> UpstreamSessionRewrite`。
- Rewriter 入口：`Rewriter::rewrite_body_with_stateful_completion(..., upstream_session_rewrite, ...)`。
- 管理端字段：`upstream_session_pool_active_count`、`upstream_session_pool_capacity`、`upstream_session_pool_oldest_last_seen_ms`、`upstream_session_pool_newest_last_seen_ms`。

### 3. Contracts

- 上游 session 池只影响最终发往 Anthropic 的 Claude Code `/v1/messages` body/header；账号选择、sticky、RPM admission、队列和内部日志仍必须使用真实下游 session。
- 池成员必须来自真实进入 gateway 的 Claude Code session id，不能随机预生成，也不能按时间窗口合成。
- Gateway 必须先完成账号选择、并发槽位和 RPM admission，再解析 upstream session pool；解析结果进入 body rewrite，且必须早于 CCH、`cc_version` 和 `X-Claude-Code-Session-Id` 生成。
- Redis 实现必须用 Lua 或等价原子机制覆盖懒清理、LRU 容量收敛、成员判断、显式映射校验、入池和 TTL 刷新；MemoryStore 必须用 mutex 保持同等语义。
- 首次池满映射按活跃成员稳定排序后用 `stable_upstream_session_hash(real_session_id) % active_count` 选择，并保存 `real_session_id -> upstream_session_id` 显式映射；只要目标仍活跃，成员集合变化不能让同一真实 session 重新取模。
- 容量缩小时必须按 `(last_seen, session_id)` 从旧到新淘汰，下一次 resolve/status 后活跃成员数不得超过当前容量；指向过期或被淘汰目标的映射必须立即逻辑失效。
- `mapped_request` 会刷新被借用 upstream session 的 `last_seen`；`owner_only` 只在真实 session 自己是池成员且发起请求时刷新。
- Redis 或 cache 解析异常必须失败开放：记录脱敏 warn，保持真实 session 发上游，不阻断用户请求。
- 本地 stateful message cache key 必须优先使用真实 session；共享 upstream session 不能让多个真实 session 共用本地 cache 状态。
- 只有池解析结果满足 `real_session_id != upstream_session_id`、即 body session 确实改变时，才覆盖 `X-Claude-Code-Session-Id`；admitted/owner-hit 和 warmup 特殊路径不得被无条件规范化。
- 自动 message telemetry 必须从改写后的最终 body 构造 context，使 request/result event 与实际覆盖后的 body/header 使用同一 upstream session。
- 客户端原生 event_logging 只能只读复用已保存且目标仍活跃的 session 映射，`allow_insert=false`，不得创建成员、刷新 TTL 或按当前成员集合临时重新取模；找不到映射、池为空或 cache 出错时失败开放。
- 日志只能输出短 session hash、账号 id、容量、动作和原因，不得输出完整 `metadata.user_id`、完整 session id 或完整请求体。
- Accounts UI 必须同步 `web/src/api.ts` 类型和 `Accounts.vue` 表单/列表展示；保存前可做基础校验，但以后端校验为最终真相。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 老账号或新账号默认配置 | `upstream_session_pool_enabled=false`，上游 session 保持旧行为 |
| `upstream_session_pool_size=0` | 后端规范化为关闭，等价 `enabled=false` |
| 容量小于 0 或大于 20 | 管理 API 返回 `BadRequest` |
| TTL 小于 5 或大于 1440 | 管理 API 返回 `BadRequest` |
| 刷新策略未知 | 管理 API 返回 `BadRequest` |
| 池未满且主请求带真实 session | 真实 session 入池并作为 upstream session |
| 池已满且新真实 session 请求 | 请求继续，body/header 复用池内已有 upstream session |
| 容量从 5 调小到 2 | 下一次 resolve/status 淘汰最久未活跃成员，活跃数收敛到 2 |
| 已保存映射的其他成员加入或过期 | 目标仍活跃时继续复用原 upstream session，不重新取模 |
| 已保存映射目标过期或被淘汰 | 旧映射失效；主请求可重新映射，event_logging 只读 lookup 返回无映射 |
| Redis pool 解析失败 | 失败开放，记录脱敏 warn，使用真实 session 发上游 |
| event_logging 只有根级 session 字段且无 `events` 数组 | 递归尝试只读映射，不能因为结构不标准而直接绕过 |
| event_logging session 无映射或池为空 | 保持现有遥测改写行为，不创建池成员，不阻断请求 |

### 5. Good/Base/Bad Cases

- Good：账号容量为 3，前 3 个真实 session 进入后成为池成员，第 4 个真实 session 稳定映射到其中一个成员；sticky、RPM 和队列仍按第 4 个真实 session 计算。
- Good：第 4 个真实 session 的显式映射目标仍活跃时，即使其他池成员发生增删，它仍复用原 upstream session；容量缩小时优先淘汰 `last_seen` 最旧成员。
- Good：`mapped_request` 下借用请求会延长被借用 upstream session 的 TTL，减少上游会话边界变动；`owner_only` 下借用请求不刷新 TTL，便于池自然轮换。
- Good：stateful cache 日志只输出短 hash，cache key 内部用真实 session 隔离，不把共享 upstream session 暴露到日志。
- Base：功能关闭或容量为 0 时，rewriter 仍只改写 `device_id` / `account_uuid`，保留原始 session 语义。
- Bad：在账号选择或 RPM admission 前用 upstream session 替换真实 session，会把多个下游 session 合并到同一个 sticky/RPM 维度。
- Bad：event_logging 映射时使用 `allow_insert=true`，会让没有主请求的遥测 payload 扩大上游 session 池。
- Bad：event_logging 没有显式映射时按当前成员重新取模，会让延迟遥测和对应主请求使用不同 upstream session。
- Bad：无条件用 body session 覆盖所有 `/v1/messages` header，会抹平抓包中 warmup probe 的合法特殊行为。
- Bad：stateful cache key 直接从最终 body 取 session，会让多个真实 session 因共享 upstream session 而污染本地 cache 状态。

### 6. Tests Required

- `src/store/memory.rs` 单测覆盖：容量上限、LRU 缩容、显式映射在其他成员变化时稳定、目标失效、只读 lookup 不创建/不刷新/不重哈希、两种刷新策略和 TTL 懒清理。
- Redis Lua 变更需人工核对原子脚本，必要时补集成测试；至少确认并发入池不超容量、缩容后不返回被淘汰目标、只读遥测不写状态。
- Gateway/Rewriter 单测覆盖：JSON/legacy `metadata.user_id.session_id` 改写、只在池实际改变 session 时对齐 `X-Claude-Code-Session-Id`、自动 telemetry 与最终 body/header 一致、无改写时保留 header、stateful cache key 使用真实 session、event_logging 递归只读映射和无 `events` 数组路径。
- `src/store/account_store.rs` / integration 测试覆盖账号字段 create/update/list round trip。
- 管理端变更必须跑 `cd cc2api/web && npm run build`，确认 TypeScript 类型和 `Accounts.vue` 同步。
- 完整检查至少跑 `cd cc2api && cargo fmt --check && cargo test`；协议改写触碰 CCH 顺序时额外跑 `cargo test cch`。

### 7. Wrong vs Correct

#### Wrong

```rust
let upstream = account_svc
    .resolve_upstream_session_pool(&account, &real_session_id, true)
    .await?;
let session_hash = generate_session_hash(..., upstream.upstream_session_id.as_deref());
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
```

这样会用 upstream session 污染 sticky 和 RPM 维度。

```rust
account_svc
    .resolve_upstream_session_pool(&account, telemetry_session_id, true)
    .await?;
```

这样会让遥测请求创建新的上游池成员。

#### Correct

```rust
let session_hash = generate_session_hash(...); // 真实下游 session
let admission = acquire_account_admission(&account, sticky, &session_hash, timeout, slot_units).await?;
let upstream_rewrite = build_upstream_session_rewrite(&account, path, &body_map, client_type).await;
let (rewritten_body, completion) = rewriter.rewrite_body_with_stateful_completion(
    body,
    path,
    &account,
    client_type,
    env_pt,
    cache_ttl,
    message_cache,
    order_enabled,
    &disabled_thinking,
    &upstream_rewrite,
    sanitizer,
);
```

```rust
account_svc
    .resolve_upstream_session_pool(&account, telemetry_session_id, false)
    .await?;
```

## Scenario: Gateway 账号槽位与 RPM Admission 顺序

### 1. Scope / Trigger

- Trigger：修改 `GatewayService::handle_request_inner` 中账号选择、账号级 FIFO 队列、请求槽位权重、RPM admission、429 重试或本地拦截顺序时适用。
- 目标：RPM 计数表示“已经获得账号执行槽位、即将进入上游转发链路”的请求数，而不是“进入本地等待队列”的请求数；账号并发槽位使用标准槽位语义展示，内部用整数单位支持 Haiku 半槽。

### 2. Signatures

- 槽位入口：`AccountService::get_or_create_queue(account.id, account.concurrency).await`
- 请求权重：`request_slot_units(path, body) -> u32`；`/v1/messages` 且 `body.model` 小写包含 `haiku` 时返回 `HAIKU_REQUEST_SLOT_UNITS = 1`，其他真实上游请求返回 `DEFAULT_REQUEST_SLOT_UNITS = 2`
- 等待入口：`AccountQueue::acquire(timeout, slot_units).await -> Result<AccountSlotPermit, QueueWaitError>`
- RPM 入口：`AccountService::acquire_account_rpm(account, sticky, session_hash).await -> Result<(), AppError>`
- RPM 状态：`AccountService::get_account_rpm_status(account).await -> AccountRpmStatus`
- 管理端实时并发字段：`current_concurrency`（标准槽位，可小数）、`current_concurrency_units`、`max_concurrency_units`、`active_requests`、`queued_requests`、`queued_request_units`

### 3. Contracts

- `Account.concurrency` 的外部语义是标准并发槽位数；管理员填 `5` 表示最多 5 个普通请求，而不是内部单位数。
- 内部单位固定为 `1 标准槽 = 2 内部单位`；普通/Opus 请求占 2 单位，Haiku 请求占 1 单位。不要把 `concurrency` 存成或显示成翻倍值。
- Gateway 正常上游路径必须先计算 `slot_units` 并获得 `AccountSlotPermit`，再调用 `acquire_account_rpm`。
- 本地拦截路径（assistant prefill、warmup、Auto Mode classifier、telemetry 假响应等）必须在账号槽位获取前返回，不得新增并发槽位消耗。
- 处于 `AccountQueue::acquire(...)` 等待阶段的请求不得递增 RPM。
- 等待队列容量仍按请求数计，保持 `2 × concurrency` 个等待请求；不要按半槽权重扩大为 `4 × concurrency`。
- `AccountQueue` 必须使用 `Semaphore::acquire_many_owned(slot_units)` 保持 Tokio semaphore FIFO 公平性。若队首普通请求需要 2 单位而当前只剩 1 单位，后续 Haiku 请求不得绕过队首。
- 调度的满载判断和 `concurrency_pct` 必须按内部单位计算：`(active_units + waiting_units) / max_units × 100`。
- `QueueWaitError::QueueFull` / `QueueWaitError::Timeout` / `QueueWaitError::Closed` 发生时，该账号 RPM 不得变化。
- 非粘性请求拿到槽位后若 RPM 饱和并返回 `AppError::ServiceUnavailable`，必须释放当前账号槽位并排除该账号后重新选号。
- 粘性请求拿到槽位后若 RPM 饱和，仍按 `acquire_account_rpm` 的等待/本地 429 语义处理，不得随意切号。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 普通请求进入真实上游路径 | 占 2 内部单位，管理端标准槽位 +1 |
| Haiku `/v1/messages` 进入真实上游路径 | 占 1 内部单位，管理端标准槽位 +0.5 |
| 排队等待槽位 | `queued_requests` 和 `queued_request_units` 可增加，RPM `current` 不增加 |
| 队首普通请求等待 2 单位且只剩 1 单位 | 后续 Haiku 不插队，直到队首请求获得 2 单位或退出 |
| 成功获得槽位且 RPM 未满 | RPM `current += 1`，permit 交给 `SlotReleaseGuard` / `SlotGuardBody` |
| 队列满 | 返回/换号前不消耗 RPM |
| 槽位等待超时 | 返回/换号前不消耗 RPM |
| 管理员缩小并发 | 已有请求不被中断；后台 shrinker 在 permit 释放后吞掉多余内部单位 |
| 非粘性 RPM 饱和 | 释放已获槽位，排除账号并重新选号 |
| 粘性 RPM 饱和 | 保持粘性账号等待；超时后返回本地 429 |

### 5. Good/Base/Bad Cases

- Good：请求 A 占满账号槽位，请求 B 在 FIFO 队列等待；B 等待期间 RPM 不变，A 释放后 B 获得槽位并通过 RPM admission 才递增。
- Good：账号并发为 5 时内部容量为 10；9 个 Haiku 占 9 单位后，新 Opus/普通请求需要 2 单位，必须等待。
- Base：`rpm_limit = 0` 时保持不限 RPM，槽位顺序仍由 `AccountQueue` 控制。
- Bad：把 `slots` 容量直接改成 `2 × concurrency` 却仍让每个请求只 acquire 1 个 permit，会让所有请求都变成半槽。
- Bad：在 `queue.acquire(...)` 前调用 `acquire_account_rpm(...)`，会让排队中或最终超时/队列满的请求提前消耗 RPM。

### 6. Tests Required

- 覆盖等待中请求不增加 `get_account_rpm_status(...).current`。
- 覆盖等待请求获得槽位并通过 RPM admission 后才递增。
- 覆盖 `QueueFull` 和 `Timeout` 不消耗 RPM。
- 覆盖普通请求占 2 单位、两个 Haiku 共享 1 个标准槽位、混合请求按内部单位满载。
- 覆盖队首普通请求需要 2 单位时，后续 Haiku 不绕过队首请求。
- 覆盖等待队列容量仍按请求数限制，不因 Haiku 半槽放大。
- 覆盖缩容不强杀已有请求，并在释放后收敛到新的内部单位容量。
- 覆盖管理 API 返回标准槽位和内部单位字段，前端类型与展示同步。
- 保留非粘性 RPM 饱和换号、粘性 RPM 饱和等待/拒绝、429 后释放槽位的回归测试。

### 7. Wrong vs Correct

#### Wrong

```rust
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
let permit = queue
    .acquire(SLOT_WAIT_TIMEOUT, DEFAULT_REQUEST_SLOT_UNITS)
    .await?;
```

```rust
let slots = Semaphore::new((account.concurrency * SLOT_UNIT_SCALE) as usize);
let permit = slots.acquire_owned().await?;
```

#### Correct

```rust
let slot_units = request_slot_units(&path, &body_map);
let permit = queue.acquire(SLOT_WAIT_TIMEOUT, slot_units).await?;
account_svc.acquire_account_rpm(&account, sticky, &session_hash).await?;
```

```rust
let slots = Semaphore::new((account.concurrency * SLOT_UNIT_SCALE) as usize);
let permit = slots.acquire_many_owned(slot_units).await?;
```

## Scenario: OAuth Usage Scoped 模型窗口

### 1. Scope / Trigger

- Trigger：修改 `service::oauth::fetch_usage`、`GatewayService` 被动用量采集、`AccountService::refresh_usage`、`UsagePollerService`、`web/src/api.ts`、`Accounts.vue` 中 usage 解析或展示时适用。
- 背景：Claude Code 新版 usage API 可能把模型专属周用量放在 `limits[]` 的 scoped 结构里，而不是顶层 `seven_day_<model>` 字段。

### 2. Signatures

- 上游接口：`GET https://api.anthropic.com/api/oauth/usage`
- 后端入口：`service::oauth::fetch_usage(token, proxy_url).await -> Result<serde_json::Value, AppError>`
- 账号刷新：`AccountService::refresh_usage(id).await -> Result<serde_json::Value, AppError>`
- 被动解析：`gateway::extract_passive_usage(headers) -> Option<serde_json::Value>`
- 被动写入：`AccountService::update_passive_usage(id, partial, UsageObservationKind).await -> Result<(), AppError>`
- 管理端接口：`POST /admin/accounts/:id/usage -> { status: "ok", usage }`
- 前端类型：`UsageData` 包含 `five_hour`、`seven_day`、`seven_day_sonnet`、`seven_day_fable`、`limits`

### 3. Contracts

- `five_hour` / `seven_day` / `seven_day_sonnet` 仍按顶层窗口读取，窗口最少包含 `utilization`，`resets_at` 可为空。
- Fable 周用量必须稳定暴露为 `seven_day_fable`；若上游没有顶层 `seven_day_fable`，从 `limits[]` 中匹配：
  - `kind == "weekly_scoped"` 或 `group == "weekly"`
  - `scope.model.display_name == "Fable"`，或 `scope.model.id` 包含 `fable`
  - `percent` 写入 `utilization`
  - `resets_at` 为字符串时保留，否则写 `null`
- 后端归一化只能补稳定字段，不得删除 `limits`、`spend`、`extra_usage` 等原始字段，方便排查上游变化。
- 前端展示应优先读取稳定字段；为了兼容旧缓存，也可从 `usage_data.limits` 回退提取 Fable。
- Gateway 必须从 Anthropic unified 响应头被动解析 `5h`、`7d` 与 Fable 专属 `7d_oi`；`7d_oi` 归一化为稳定字段 `seven_day_fable`。窗口必须同时具备合法 `utilization` 与未来合理范围内的 `reset`，缺失或异常时不得覆盖已有数据。
- 普通业务请求无论成功或 429 都不得调用 usage API。主动查询只允许两个显式入口：`auto_poll_usage=true` 的 active OAuth 账号由 `UsagePollerService` 定时刷新，以及管理员手动调用 `/admin/accounts/:id/usage`。
- 成功响应、PrimePoller 成功和显式 usage 查询使用 `UsageObservationKind::Allowed`；429 使用按窗口构造的 `RejectedWindows`。窗口 `status=rejected` 时视为拒绝，`status=allowed` 时明确视为允许；缺少明确状态时才用 `surpassed-threshold=true/正数` 或 `utilization >= 1.0` 兜底。旧 reset 已到期、新 reset 已推进，且窗口本身未被拒绝时，若旧值和新值仍处于 97% 以上高位，必须保存新 reset 并把首次新周期 utilization 归零；只有真实拒绝窗口保留高位值。
- 被动与主动写入都必须保留本次观察未包含的窗口和扩展字段，包括 `seven_day_sonnet`、`limits`、`spend`、`extra_usage`。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| `limits` 缺失或不是数组 | 不补 `seven_day_fable`，保留原始 usage |
| `limits` 前置项 `scope: null` | 跳过该项，继续查找后续 scoped 项 |
| Fable scoped 项 `percent` 非数字 | 不补窗口，避免 UI 展示脏值 |
| Fable scoped 项 `resets_at: null` | 窗口保留 `resets_at: null`，前端显示 `—` |
| 顶层已有 `seven_day_fable` 对象 | 保留顶层对象，不用 `limits` 覆盖 |
| 成功响应携带完整 `7d_oi` | 被动写入 `seven_day_fable`，不调用 usage API |
| 429 携带完整 `7d_oi` 且该窗口 `status=rejected` | 按拒绝样本持久化；Fable 耗尽只影响 Fable 模型族 |
| 5h 触发 429，7d/Fable 窗口为 `status=allowed` 且携带跨周期高位值 | 仅 5h 参与限流；7d/Fable 保存新 reset 并将首次 utilization 归零 |
| 旧 99%/100% reset 已到期，成功样本给出新 reset 但仍是高位 | 新 reset 保留，首次 utilization 写 0 |
| 同一新 reset 的后续完整样本 | 按响应头真实值正常更新 |
| `auto_poll_usage=false` | 后台 poller 不查询该账号 usage |
| 管理员手动刷新或 `auto_poll_usage=true` | 允许主动查询 usage，结果仍经过 rollover 合并 |
| 上游返回 401/403/429 | 维持现有 `AppError` 分类，不吞错误体 |

### 5. Good/Base/Bad Cases

- Good：usage 先返回 session/weekly all 两个 `scope: null` limit，后返回 Fable scoped limit；解析器跳过前两项并补出 `seven_day_fable`。
- Good：Fable 成功响应带 `7d_oi utilization/reset`，Gateway 收到响应头后异步写入 `seven_day_fable`，整个请求生命周期不访问 usage API。
- Good：旧 7d 为 99% 且 reset 已过期，下一次成功响应把 reset 推到下周但仍回 99%；合并层保存新 reset 并返回 0%，后续同 reset 的真实样本可继续更新。
- Base：只返回传统 `five_hour` / `seven_day`；保留已有 Fable 数据，不主动补查。
- Bad：直接假设 `limits[0]` 就是 Fable，或遇到第一个 `scope: null` 用 `?` 提前返回，导致真实 Fable 项被漏掉。
- Bad：在 Fable body EOF 或 429 后自动调用 usage API，绕过 `auto_poll_usage` 显式开关。
- Bad：只看新 reset 在未来就相信仍为 99%/100% 的成功样本，会把上一周期用量重新带入新周期。

### 6. Tests Required

- `service::oauth` 单测覆盖：前置 `scope: null` 项、Fable scoped 项、已有顶层 `seven_day_fable` 不覆盖、非 Fable scoped 项忽略。
- `service::gateway` 单测覆盖：5h/7d/7d_oi 完整解析、秒/毫秒 reset、缺失字段、非法数值和异常时间。
- `service::account` 单测覆盖：Allowed rollover 高位清零、已下降值采用、同周期后续更新、RejectedWindows 仅保留明确拒绝窗口高位及未观察字段不丢失。
- `service::gateway` 单测覆盖：429 按窗口 `status` 判定拒绝，显式 `allowed` 优先于高位 utilization，缺少 status 时兼容数值型 `surpassed-threshold`。
- 静态搜索必须确认 `refresh_usage` 只由 usage poller 和管理端手动接口等显式入口调用，不存在 Gateway 请求后刷新链路。
- `cc2api/web` 构建必须通过 `npm run build`，确保 `UsageData` 类型与 `Accounts.vue` 展示同步。
- 改动 `fetch_usage` 后至少跑 `cargo test`，确认账号调度和 usage 相关共享测试不回归。

### 7. Wrong vs Correct

#### Wrong

```rust
let model = item.get("scope")?.get("model")?;
```

#### Correct

```rust
let Some(model) = item.get("scope").and_then(|scope| scope.get("model")) else {
    continue;
};
```

## Scenario: Fable 周用量上限 fallback

### 1. Scope / Trigger

- Trigger：修改 `/v1/messages` 账号选择、sticky session、Fable 周用量识别、上游 429 分类、settings 热刷新或 Settings 页 Fable 控件时适用。
- 目标：当 OAuth 账号最近观测的 Fable 周用量达到管理员设置的全局上限时，不再向该账号分配新的 Fable 请求；低于上限的账号仍使用原 sticky、RPM 和综合评分，不做主动均衡。

### 2. Signatures

- Setting keys：`fable_sticky_quota_fallback_enabled=true`、`fable_weekly_usage_limit_percent=50`；百分比只允许 `1..=100` 的整数字符串。
- 默认常量：`DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED`、`DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT`。
- Gateway 热缓存：`reload_fable_sticky_quota_fallback_enabled()` 与 `reload_fable_weekly_usage_limit_percent()`；启动时必须各调用一次，管理端更新对应 setting 后必须 reload。
- 请求上下文：`AccountSelectionContext { fable_quota_fallback_enabled: bool, fable_weekly_usage_limit_percent: u32, request_model: Option<String> }`。
- 账号选择：`AccountService::select_account_with_selection_context(session_hash, exclude_ids, allowed_ids, context).await -> Result<SelectedAccount, AppError>`。
- 429 分类：`AccountService::handle_rate_limit_with_context(account, retry_after_secs, body, usage, context).await -> Result<RateLimitDecision, AppError>`。
- 账号可用性判断：`account_fable_weekly_usage_limit_reached(account, limit_percent) -> bool`。
- 新决策分支：`RateLimitDecision::RetryOtherAccount` 表示当前账号仅对本请求模型不可用，调用方可排除该账号后重试其他账号。

### 3. Contracts

- Gateway 只有在 `path == "/v1/messages"` 时才允许启用 Fable fallback；`count_tokens`、bootstrap、usage poller、PrimePoller 和其它入口必须保持 disabled 语义。
- Fable 模型只匹配 `claude-fable-5` 或 `claude-fable-5[...]`。不要用包含匹配覆盖其他模型名。
- Fable 周用量达到上限必须同时满足：账号为 `AccountAuthType::Oauth`、`usage_data.seven_day_fable.utilization >= context.fable_weekly_usage_limit_percent`、`resets_at` 是未来 RFC3339 时间。不要复用普通 usage 的 `USAGE_HIT_THRESHOLD = 97.0`。
- `utilization` 缺失或不是数字、`resets_at` 缺失/非法/已过期时视为未达到上限，避免脏缓存误伤账号。
- SetupToken 即使缓存里有脏的 `seven_day_fable`，也必须保持旧 sticky 行为。
- sticky 账号达到上限时，只把该账号加入本轮 `runtime_exclude_ids`，并刷新原 sticky TTL；不要删除旧 sticky。只有替代账号真实承载请求后，才通过已有 `should_bind_session` / `bind_selected_session` 覆盖 sticky。
- 非 sticky Fable 请求应先过滤达到上限的账号；若所有允许候选都达到上限，返回包含配置百分比的 `AppError::TooManyRequests`，不要落到普通 `ServiceUnavailable("no available accounts")` 或回退到已达上限账号。
- 低于上限的候选继续使用现有 API Token allow/block、优先级、通用 7d/5h、并发和 RPM 逻辑；不得按 `seven_day_fable` 排序、加权或主动均衡。
- 请求开始前低于上限即可执行；单次请求使实际用量轻微越线是允许的，只有 usage 被动/主动写回后的后续请求才按新观测值过滤，不预测单次请求成本。
- sticky 账号 RPM 饱和不属于 Fable 周用量 fallback，仍走 `acquire_account_rpm` 的等待或本地 429，不能换号破坏 prompt cache。
- Fable OAuth 429 且开关启用时，先识别通用 `seven_day` / `five_hour` 窗口并写账号级冷却；若通用窗口未命中，则返回 `RateLimitDecision::RetryOtherAccount`，不要写账号全局 `rate_limit_reset_at`。
- Fable 429 如需返回 Fable reset 信息，必须使用同一请求上下文阈值；本地 usage 未达到上限时，Gateway 只能使用本次 429 的 `7d_oi` 响应头做被动采集和模型级换号，不得触发 usage API。
- 新增 `RateLimitDecision` 分支后，所有 `match RateLimitDecision` 的调用方必须显式处理 `RetryOtherAccount`，不能把它误当成 `Quarantined`。
- 新 setting 必须同步默认常量、SQLite/PostgreSQL 共用的缺失键插入、管理 API GET/PUT 校验、Gateway 启动加载/保存后热刷新和 Settings 数字控件；非法存量值在 service reload 时回退默认 `50`，热路径不得 panic。
- 设置为 `100` 可恢复此前明确 100% 才过滤的阈值语义；关闭 `fable_sticky_quota_fallback_enabled` 可完全停用本规则，且二者都应热生效。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| 开关开启、阈值 50，sticky OAuth usage 为 50% 且 reset 在未来 | 本轮排除 sticky 账号，尝试选择替代账号 |
| 开关开启、阈值 50，sticky OAuth usage 为 49% | 保持原 sticky 账号 |
| 开关关闭，同样的 sticky 账号 usage 为 100% | 保持原 sticky 账号 |
| Fable sticky 达到上限且没有替代账号 | 返回 `TooManyRequests`，旧 sticky 绑定保留 |
| 非 sticky 候选分别为 50% 和 49% | 过滤 50% 账号，49% 账号进入既有评分 |
| 所有允许候选都达到上限 | 返回包含阈值的 `TooManyRequests` |
| 阈值 100，usage 为 99% / 100% | 99% 允许，100% 过滤 |
| 非 Fable 模型请求 | 忽略 `seven_day_fable`，保持普通 sticky / 调度行为 |
| SetupToken 账号带 `seven_day_fable` 脏缓存 | 忽略该窗口，保持 sticky |
| Fable 窗口缺失、非法或 reset 已过期 | 视为未达到上限 |
| sticky 账号 RPM 饱和 | 不触发 Fable fallback，保持等待/本地 429 |
| Fable OAuth 429 命中 `seven_day` 或 `five_hour` | 写账号级冷却并返回 `Quarantined` |
| Fable OAuth 429 未命中通用窗口 | 返回 `RetryOtherAccount`，不写全局冷却 |
| setting 为 `0`、`101`、小数或文本 | 管理 API 返回 `BadRequest`，旧配置不变 |

### 5. Good/Base/Bad Cases

- Good：阈值为 50，用户会话 sticky 到账号 A，A 的 `seven_day_fable` 为 50% 且 3 天后 reset；同 token 允许 49% 的账号 B，Gateway 对本次请求选择 B，真实上游成功后把 session 绑定到 B。
- Good：A 的普通周限额 `seven_day` 也为 100%；Fable 429 必须隔离 A 到通用 reset 时间，而不是继续换号重试导致所有模型都反复撞墙。
- Base：没有 `request_model`、模型不是 Fable、开关关闭或 Fable 窗口无效时，`AccountSelectionContext::disabled()` / 窗口校验保持旧行为。
- Bad：继续把固定 `100` 写死在账号 helper 中，会让管理员保存的百分比只在 UI 显示而不影响调度。
- Bad：把通用 `USAGE_HIT_THRESHOLD = 97.0` 当成 Fable 上限，或根据预估消耗提前留缓冲，都会绕过管理员设置的明确控制线。
- Bad：发现 sticky Fable 达到上限后直接 `delete_session`，没有替代账号时用户后续非 Fable 请求也会丢失原 sticky。

### 6. Tests Required

- `tests/account_scheduler_test.rs` 覆盖：49% 保持 sticky、50% 选择替代账号、替代账号可重绑、无替代账号返回 429 且旧 sticky 保留、非 sticky 过滤、所有候选达到上限、开关关闭、阈值 100、非 Fable 和 SetupToken。
- `src/service/account.rs` 单测覆盖：配置阈值比较、未来/过期/缺失/非法窗口、SetupToken 忽略，以及 Fable OAuth 429 的 `RetryOtherAccount`、通用 `seven_day` / `five_hour` `Quarantined` 和 credit 行为。
- `src/store/db.rs` / `src/handler/router.rs` / `src/service/gateway.rs` 覆盖：默认 key 为 `50`、非法值拒绝、合法保存后热刷新、非法存量值 reload 回退默认。
- Settings 改动后必须运行 `cc2api/web` 的 `npm run build`，确保数字控件、校验和 `SettingsMap` 可构建。
- 后端改动后至少运行 `cargo fmt --check`、`cargo test`；settings / handler / gateway 同时改动时再跑 `git diff --check`。
- 静态搜索确认普通 Gateway 请求没有新增 `refresh_usage` 调用，且未在账号评分中引入 `seven_day_fable`。

### 7. Wrong vs Correct

#### Wrong

```rust
if check_usage_window(&account.usage_data, "seven_day_fable", 100.0).is_some() {
    self.cache.delete_session(session_hash).await?;
    exclude_ids.push(account.id);
}
```

```rust
match rate_limit_decision {
    RateLimitDecision::Quarantined | RateLimitDecision::RetryOtherAccount => return last_resp,
    _ => {}
}
```

#### Correct

```rust
if context.is_fable_quota_fallback_active()
    && account_fable_weekly_usage_limit_reached(
        &account,
        context.fable_weekly_usage_limit_percent,
    )
{
    runtime_exclude_ids.push(account.id);
    let _ = self
        .cache
        .set_session_account_id(session_hash, account.id, STICKY_SESSION_TTL)
        .await;
}
```

```rust
match rate_limit_decision {
    RateLimitDecision::RetryOtherAccount => exclude_ids.push(account.id),
    RateLimitDecision::Quarantined => return last_resp,
    _ => {}
}
```

## Scenario: 受信任管理端解析 OAuth 凭据

### 1. Scope / Trigger

- 修改 `POST /admin/accounts/:id/oauth-credentials/resolve`、`AccountService` OAuth refresh 锁、usage 获取 token，或新增需要消费最终 AT/RT 的受信任服务时适用。
- 该接口用于让外部 orchestrator 复用 cc2api 的单一 RT 刷新所有权，不是浏览器或普通网关 token 的公开接口。

### 2. Signatures

管理 API：

```http
POST /admin/accounts/:id/oauth-credentials/resolve
Authorization: Bearer <admin password>
Content-Type: application/json

{
  "min_validity_seconds": 2400,
  "force_refresh": false
}
```

响应：

```json
{
  "account_id": 1,
  "access_token": "<secret>",
  "refresh_token": "<secret>",
  "expires_at": 0
}
```

service 入口：

```rust
AccountService::resolve_oauth_credentials(
    id: i64,
    min_validity_seconds: i64,
    force_refresh: bool,
) -> Result<OAuthCredentialSnapshot, AppError>
```

### 3. Contracts

- handler 默认 `min_validity_seconds=2400`，只允许 `60..=7200`；`force_refresh` 默认 false。
- 只接受 `status=active` 且 `auth_type=oauth` 的账号，AT、RT、`expires_at` 任一缺失都拒绝返回。
- 每次 resolve 都必须获取 `oauth:refresh:account:<id>` cache lock，即使当前 AT 仍有效也不能走无锁快路径；这样返回快照不会与 Gateway、usage poller 或另一个 resolve 的 RT 轮换并发。
- 获锁后重新读取账号；需要刷新时复用同一 refresh 实现并落库；返回前再次读取账号，确保 AT/RT/过期时间来自同一次最终存储状态。
- `force_refresh=true` 只用于消费者已经观察到 401 的单次恢复。调用方不得用它做周期轮询，也不得自行拿响应 RT 调 OAuth endpoint。
- 现有 `resolve_upstream_token` 继续允许刷新失败时使用仍有效 AT 的兼容 fallback；管理端 resolve 不允许返回不满足最小有效期的旧快照。
- `refresh_usage` 通过同一 token resolve 链路获取 AT，避免 usage poller 与管理端消费者形成第二条无锁刷新路径。
- tracing、错误和测试输出不得记录 AT、RT、Authorization、邮箱/UUID 的真实映射。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|------|------|
| `min_validity_seconds < 60` 或 `> 7200` | `BadRequest` |
| 账号不存在 | 现有 store 的 not found 错误 |
| 账号 disabled | `BadRequest`，提示不是 active |
| SetupToken 账号 | `BadRequest`，提示不是 OAuth |
| AT 剩余时间满足要求 | 仍获取账号锁，最终重读后原样返回 |
| AT 临期或 `force_refresh=true` | 锁内刷新、落库、最终重读后返回 |
| refresh token 缺失 | 更新 auth error，返回不可用错误 |
| refresh 返回 `invalid_grant` | 返回错误，不使用旧 RT/AT 伪装成功 |
| 等待锁超时 | `ServiceUnavailable`，不返回锁前快照 |

### 5. Good/Base/Bad Cases

- Good：Gateway 正在轮换 RT，bench resolve 等待同一 lock；锁释放后重新读库并拿到新 AT/RT，而不是返回进入函数时的旧副本。
- Base：AT 仍有 1 小时有效期，resolve 获取锁后不发 refresh 请求，只最终重读并返回当前快照。
- Bad：先检查 `has_valid_oauth_access_token`，有效就直接返回；检查后到返回前另一个刷新者可能已经轮换 RT。
- Bad：管理端 resolve 刷新失败后返回仍有效旧 AT；bench 会把不满足本次运行窗口的凭据当作已准备完成。

### 6. Tests Required

- handler 单测覆盖默认值、60/7200 边界和越界拒绝。
- service 单测覆盖有效 AT 不刷新但仍返回完整快照、非 OAuth/disabled 拒绝。
- 人工占用账号 refresh lock，启动 resolve 后断言其等待；更新 store 的 AT/RT 并释放锁，断言返回更新后的最终快照。
- refresh 成功/失败路径断言 lock 总会释放，响应和日志不包含额外账号字段。
- 完整改动至少运行 `cargo fmt --check` 和 `cargo test`。

### 7. Wrong vs Correct

#### Wrong

```rust
let account = self.store.get_by_id(id).await?;
if account.has_valid_oauth_access_token(min_validity_seconds) {
    return Ok(snapshot_from(account));
}
```

#### Correct

```rust
let lock_key = format!("oauth:refresh:account:{}", id);
let lock_owner = Uuid::new_v4().to_string();
let acquired = self
    .cache
    .acquire_lock(&lock_key, &lock_owner, OAUTH_LOCK_TTL)
    .await?;
if acquired {
    let result = self.resolve_oauth_credentials_locked(id, policy).await;
    self.cache.release_lock(&lock_key, &lock_owner).await;
    return result;
}
```

有效 AT 也必须在同一账号锁内最终重读后返回。

## Scenario: 有效上游 Session 首次 Hello 代理探测

### 1. Scope / Trigger

- Trigger：修改 Claude Code `/v1/messages` 首次连通性检查、账号代理网络路径、上游 Session 池解析、Session 去重、CacheStore/Redis singleflight、严格模式或对应 Settings 时适用。
- 目标：新的有效上游 Session 第一次准备承载上游请求时，通过最终选中账号的 `proxy_url` 匿名探测 Anthropic Hello；同一活跃上游 Session、账号和代理路径只探测一次。
- 公开 `GET/HEAD /api/hello` 仍是无状态本地健康端点，不进入账号选择或代理探测；完整 wire 画像见 `../protocol/claude-code-profile-upgrade.md`。

### 2. Signatures

- 服务入口：`SessionHelloProbeService::ensure_ready(account, real_session_id, upstream_session_id, config).await -> SessionHelloProbeDecision`。
- 决策：`Proceed`、`BlockFailure`、`BlockTimeout`、`BlockUnavailable`。
- CacheStore：`get_session_hello_probe_state(key, success_ttl)`、`set_session_hello_probe_state(key, state, ttl)`，并复用 owner 语义的 `acquire_lock/release_lock`。
- 状态 key：`session_hello_probe:v1:<account_id>:<sha256(upstream_session_id)>:<sha256(proxy_url)>`。
- 全局 settings：
  - `session_hello_probe_enabled=false`
  - `session_hello_probe_strict=false`
  - `session_hello_probe_timeout_secs=5`，范围 `1..=30`
  - `session_hello_probe_success_ttl_secs=3600`，范围 `60..=86400`
  - `session_hello_probe_failure_cooldown_secs=300`，范围 `10..=3600`

### 3. Contracts

- 仅当 path 精确为 `/v1/messages`、客户端为 Claude Code、原始 body 能提取非空真实 Session，且请求已经选定账号并完成本轮 slot/RPM admission 时调用探测。
- Gateway 必须先解析账号级上游 Session 池，再调用探测；探测使用最终改写后的有效上游 Session 去重。池关闭或解析失败时回退到真实下游 Session，不得因池故障阻断原有业务转发。
- assistant prefill、warmup、classifier、event logging、count tokens、普通 API 客户端和其它本地响应不得创建探测状态。
- 探测请求固定为匿名 `HEAD https://api.anthropic.com/api/hello`，header 为 `User-Agent: Bun/1.4.0`、`Accept: */*`、`Accept-Encoding: gzip, deflate, br, zstd`、`Connection: keep-alive`；不得添加 query、body、Authorization、Cookie、billing header 或用户数据。
- 非空 `Account.proxy_url` 必须先通过 `reqwest::Proxy::all` 校验，再交给 `tlsfp::get_request_client`；无效代理不得静默直连。空代理允许直连。
- 只有 HTTP 200 为成功。成功状态命中时原子续期，形成滑动空闲 TTL；`failure` / `timeout` 使用固定冷却，不因读取续期。
- 状态不存在时，leader 获取 `:lock` 后执行网络请求并写状态；follower 轮询同一状态并复用结果。RedisStore 必须保证跨进程去重，MemoryStore 只保证单进程。
- leader 写状态失败时不得立即释放锁，应让锁按 TTL 自然过期以吸收当前并发波次；已经等待过该 leader 的 follower 即使随后拿到锁也不得再次发包，非严格模式开放、严格模式返回 503。新的后续请求可在锁释放或过期后恢复探测。
- MemoryStore 必须按固定间隔惰性清理所有过期探测状态，不能只清理当前访问键，也不能在每次读写时全表扫描。
- 探测不得再次执行账号 RPM admission，也不得写业务 usage 或自动 telemetry。账号 retry 从 A 切到 B 时，B 的账号 id 生成新 key，必须在 B 承载业务请求前重新判断。
- 日志只允许账号 id、真实下游 Session 短 hash、有效上游 Session 短 hash、`proxy_configured`、`source=network|cache|follower`、耗时、HTTP status 和结果类别；网络结果允许使用 `info`，缓存不可用或 follower 等待超时使用 `warn`。不得输出完整 Session、代理 URL、请求/响应 body 或凭据。
- Settings 必须同步默认常量、数据库缺失键插入、管理 API GET/PUT 校验、Gateway 热加载和前端控件；功能关闭时从属控件禁用但保留已保存值。

### 4. Validation & Error Matrix

| 条件 | 非严格模式 | 严格模式 |
|------|------------|----------|
| 功能关闭 | 不读 cache、不发探测，继续业务请求 | 同左 |
| HTTP 200 | 写 `success`，继续业务请求 | 同左 |
| HTTP 非 200、代理或网络错误 | 写 `failure` 冷却并继续 | 复用冷却并返回 Anthropic 形状 502 |
| 探测超过总超时 | 写 `timeout` 冷却并继续 | 复用冷却并返回 Anthropic 形状 504 |
| cache 读写或锁失败 | 记录脱敏 `warn`，不发无去重探测并继续 | 返回 Anthropic 形状 503 |
| follower 等待后仍无结果 | 本请求不重复发包并开放；新请求可在锁过期后恢复 | 返回 503，不永久等待或重复发包 |
| 同 Session 切换账号或账号修改代理 | 使用新 key 重新探测 | 同左 |

### 5. Good/Base/Bad Cases

- Good：两个实例同时收到映射到同一有效上游 Session 的首请求，Redis 只允许一个 leader 发 Hello，follower 复用 `success`；两个业务请求各自只执行原有一次 RPM admission。
- Good：账号 A 的业务请求返回可重试错误后切换到 B，A/B 各有一个独立探测结果，B 完成自己的探测后才转发业务请求。
- Base：功能默认关闭；升级旧数据库时只插入缺失 setting，不覆盖管理员已有值，热路径保持升级前行为。
- Bad：直接按 Session 记一个永久布尔值；这会忽略账号/代理变化并无限增长。
- Bad：代理字符串无效时继续调用会忽略代理错误的 client builder，导致探测从宿主机直连成功并错误放行业务请求。
- Bad：把探测放在 admission 前或在探测内部再计一次 RPM，会让等待、失败和重试请求的 RPM 语义漂移。

### 6. Tests Required

- 请求构造测试断言精确 method、URL、headers、空 body，以及无 Authorization、Cookie、billing header；配置有效代理时必须由本地 mock proxy 实际收到请求。
- Probe service 覆盖 200、非 200、超时、无效代理不直连、缓存故障的严格/非严格决策、失败冷却复用和状态 key 不泄漏原值。
- MemoryStore 覆盖成功滑动续期、失败固定冷却、未再次访问的过期键会被低频惰性清理，以及并发首请求只发一次。
- Probe service 覆盖 leader 写缓存失败时 follower 不重复探测，并验证锁到期后的新请求可以恢复探测。
- Redis 集成测试必须连接真实 Redis，使用两个独立 RedisStore/服务实例并发断言只产生一次网络探测，同时验证成功续期与失败不续期。
- Gateway 集成测试覆盖账号 A retry 到 B 时 Hello 调用为 2 次、两个账号 RPM 各只增加 1；共享有效上游 Session 只探测一次；池关闭或解析失败时回退真实 Session；非严格失败继续业务、严格失败不发送业务请求；本地拦截、count tokens、API 客户端和缺失 Session 不进入探测。
- Settings 覆盖默认值、布尔/数值范围、保存后热加载；前端运行 `npm run build`。
- 完整验证运行 `cargo fmt --check`、`cargo test`、`cargo test cch`、`git diff --check`，并静态扫描日志不得包含完整代理地址、Session 或凭据。

### 7. Wrong vs Correct

#### Wrong

```rust
let client = get_request_client(&account.proxy_url);
let response = client.head(HELLO_URL).send().await?;
account_svc.acquire_account_rpm(&account, sticky, session_hash).await?;
```

无效代理可能被 client builder 忽略，而且探测后再次 admission 会把一轮业务请求计成两次 RPM。

#### Correct

```rust
let state = if !account.proxy_url.is_empty()
    && reqwest::Proxy::all(&account.proxy_url).is_err()
{
    SessionHelloProbeState::Failure
} else {
    run_anonymous_head(&account.proxy_url, config.timeout).await
};
```

Gateway 在既有 admission 后调用 `ensure_ready`；服务内部先拒绝无效代理，再执行匿名 HEAD、状态缓存和 singleflight，不执行第二次 RPM admission。

## 设置热刷新模式

新增全局 setting 通常要经过这些位置：

```text
src/store/settings_store.rs     默认值常量
src/store/db.rs                 首次插入默认值 / 旧值迁移
src/handler/router.rs           GET/PUT 校验与 reload 调用
src/service/gateway.rs          RwLock 缓存、reload_* 方法、热路径读取
web/src/api.ts                  前端类型或字段
web/src/components/Settings.vue 控件和文案
```

不要只在 `settings_store.rs` 加常量。漏掉 reload 会导致 UI 写入后服务仍用旧值；漏掉 migration 会导致老实例没有默认值。

## 后台任务边界

- `UsagePollerService` 负责 OAuth usage 主动刷新，不应写网关热路径状态。
- `PrimePollerService` 负责峰值预热调度，发出的请求也可能命中网关治理规则；新增拦截规则时必须说明是否影响预热。
- Telemetry 自动代发必须遵守隐私边界，不发送 prompt、tool input、响应正文、token 或 cookie。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 在 handler 里直接拼 SQL 或写调度逻辑 | 路由层膨胀，测试困难 | 放进 service/store |
| 新 setting 只改默认常量 | 老 DB、UI、热缓存不同步 | 按 settings 热刷新模式全链路更新 |
| 网关读 body 后继续转发原 request | 上游收到空 body 或旧 body | 明确重建 request body |
| 粘性会话遇到限流直接换号 | Claude Code prompt cache 被破坏 | 粘性请求等待或本地返回 |
| CCH 之前/之后插入 body 改写顺序不清 | 请求签名不匹配真实客户端 | 所有 body 改写先完成，再统一算 CCH |
