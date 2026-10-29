# 请求观测相关规范摘录

以下按原文件行段摘录，用于避免上下文注入截断。实现阶段还须按 trellis-before-dev 读取适用规范；摘录不替代原文件。

## 来源：.trellis/spec/cc2api/backend/service-architecture.md（1～126 行）

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


## 来源：.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md（1352～1376 行）

### 3. Contracts

- `claude_code_profile_selection_mode` 仅接受精确值 `client_version` 或 `account`，默认前者；不 trim、不接受空白变体。GET 补齐默认值，PUT 在任何写入前校验。无需新增环境变量。
- 客户端模式只识别以 `claude-code/` 或 `claude-cli/` 开头的原始 UA，前缀不区分大小写；取斜杠后第一个空白分隔 token，只有精确 `2.1.260`、`2.1.280`、`2.1.293` 自动匹配。
- 缺少 UA、非法 UA、Bun/axios 等辅助 UA，以及未匹配版本，均使用 `claude_code_version_profile` 指定的内置默认画像，出厂为 `2.1.293`。不得按邻近版本、请求体 `appVersion` 或其它字段推断。
- 准入策略先检查原始 UA，再于读取 body 和账号重试前冻结画像。默认回退不绕过 `allowed_user_agents`、`allowed_claude_code_versions`；准入拒绝的请求仍被拒绝。
- `account` 模式的 `resolve` 返回 `None`，沿用最终选中账号的持久 env 和旧选择规则；换号后使用新账号原有画像。客户端模式冻结的 `Some(profile)` 在 401、签名重试、换号和配置热刷新期间保持一致。
- 每次选定账号后调用 `account_for_request_profile` 生成副本，只覆盖 `version/version_base/build_time/node_version` 软件字段。旧账号 env 无法反序列化时，先使用既有 `device_profile` 归一化已知字段并保留未知字段，再覆盖软件版本；副本不得写回存储。
- 原账号用于调度、sticky、RPM/并发 admission、凭证和上游 Session 池；副本用于 headers/body、模型/beta、billing/CCH、count_tokens、bootstrap、内部 Hello、原生及自动遥测。公开 `GET/HEAD /api/hello` 继续保持无状态，不选择账号。
- 启动和 mode/default/允许范围/禁止版本/允许 UA 保存后，通过 `reload_access_profile_config` 从同一次 `get_all` 读取准入与选择配置，并在 `AccessProfileConfig` 的一把 `RwLock` 中原子替换。写锁覆盖读取和替换，防止并发 reload 的旧读取覆盖新快照；policy 解析失败保留旧快照。请求在同一读锁内先准入、再冻结画像。
- 非法存量 mode 回退 `client_version`，非法存量默认 key 回退 `2.1.293`；已冻结的客户端画像不受后续 reload 影响。旧 reload 方法委托给组合刷新。
- 数据库仅补齐缺失的 mode key：SQLite 使用 `INSERT OR IGNORE`，PostgreSQL 使用 `ON CONFLICT (key) DO NOTHING`，保留显式值。只切 mode 不写账号 env；保存默认 profile 执行上方全局事务，允许范围按模式处理。出厂组合升级边界见 [Settings & Database](../backend/settings-database.md#迁移规则)。
- 自动遥测以 `(account_id, profile_key)` 分容器，创建时固定账号副本；续期仅更新 token 和 10 分钟 TTL，不重读账号替换软件画像。请求结果和流结束回调携带同一副本，payload 与 UA 从同一容器生成。
- run/GrowthBook 运行 ID 的种子包含 profile key，同秒两版也不相同；device ID 和账号 UUID 继续共享。管理端过期时间取该账号各画像容器的最大值，发送计数仍按账号累计；容器过期只清理自身 key。

版本相关缓存必须使用以下维度；延迟提交沿用请求阶段已经捕获的 key：

| 状态 | key 契约 |
|------|----------|
| Stateful blocks | `<account_id>:<profile_key>:<real_session_id>`，保留真实下游 Session，不改成上游池 Session |
| Hello 状态和 singleflight | `session_hello_probe:v2:<account_id>:<profile_key>:<sha256(upstream_session_id)>:<sha256(proxy_url)>` |
| 非流式探针 | 既有 JSON key 增加 `profile` 字段，即使两版 headers/body 相同也隔离 |

sticky、RPM、并发与上游 Session 池容量不得因 profile 增加独立配额。

