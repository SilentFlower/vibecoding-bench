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

## Scenario: Gateway 压缩请求编解码

### 1. Scope / Trigger

- Trigger：修改通用 Gateway／count_tokens 入站读体、Content-Encoding、请求正文改写与发送、signature／认证／换号重试时适用。
- 通用转发包含 Messages、event_logging 及既有其它 JSON／非 JSON 路径；不据编码新增端点、放宽 v3 路径许可或改变各端点正文校验。响应编解码与保活沿用独立链路。

### 2. Signatures

- 请求专用模块：`service/request_body_codec.rs`；`REQUEST_BODY_LIMIT: usize = 10 * 1024 * 1024`。
- `RequestBodyEncoding` 实现 Clone／Default；`from_headers(&HeaderMap) -> Result<Self, RequestBodyCodecError>`、`is_encoded(&self) -> bool`、`content_encoding(&self) -> Option<String>`。
- async `decode(&self, body: Bytes) -> Result<Bytes, RequestBodyCodecError>`；async `encode<'a>(&self, body: &'a [u8]) -> Result<Cow<'a, [u8]>, RequestBodyCodecError>`。
- `RequestBodyCodecError` 为无字段分类：`InvalidEncoding`／`UnsupportedEncoding`／`TooLarge`／`InvalidBody`／`Internal`；Gateway 的 `request_body_codec_error_response` 映射为 Anthropic error object。
- 普通 `forward_request`、`forward_count_tokens_request` 与 `maybe_retry_signature_error` 接收同一冻结的 `&RequestBodyEncoding`；`request_headers_for_encoding(&HashMap<String, String>, &RequestBodyEncoding) -> HashMap<String, String>` 清理出站传输头。没有新 setting、环境变量、依赖、数据库或 bridge 字段。

### 3. Contracts

- Router API token 鉴权、count_tokens POST 检查和 Gateway 原始 UA 准入／画像快照保持既有优先级；编码解析和解码必须先于正文策略、账号选择、slot／RPM、Session 池、Hello 及自动遥测。
- 编码源是原始 `HeaderMap::get_all(Content-Encoding)`，不使用有损的 `extract_headers` 结果。按字段顺序及逗号列表收集，仅去 SP／HTAB，完整 ASCII token 大小写无关；容忍空项／identity，累计最多 32 个列表片段、4 个实际编码层。先验证完整声明，再逆序解码；出站省略空项／identity、小写化并保留有效顺序和 x-gzip 别名。
- 支持 gzip／x-gzip、zlib／raw-deflate 兼容、标准 br、zstd。原始字节及每层解码结果各不超过 10 MiB；标准 br 不接 large-window 扩展，zstd 首次读取前设 `window_log_max(24)`，后续 frame 同样受 16 MiB 窗口限制。窗口和输出上限不是总内存或可取消 CPU 时限。
- gzip 必须完整校验所有 member 的 CRC／ISIZE；deflate 必须 StreamEnd 且耗尽输入，zlib 格式失败才尝试严格 raw，超限不回退；br 必须严格结束且耗尽输入；zstd 支持完整多 frame／skippable frame。恰好上限仍读取并验证结尾，不能只取第一 member、宽松 EOF 或前 10 MiB。请求不复用宽松响应 helper。
- 解码后的原始逻辑字节用于客户端识别、策略、真实 Session、调度和缓存。现有身份、根键清理、池映射、有限 Session 头对齐及最终 CCH 的顺序保持；count_tokens 仍严格验证 JSON object／model，通用非 JSON 继续按原规则处理，不新增全局 schema 校验。
- 实际 codec 工作进入 blocking worker；无有效编码的 decode 保留原 Bytes，encode 借用原字节，不嗅探 magic、不根据 Accept-Encoding、UA 或画像版本主动压缩。无编码读体／非法 JSON 的原状态及错误形状保留。
- CCH 完成后，每次真正发送前按有效链正序重编码。gzip 容器可以重建，deflate 统一标准 zlib；不承诺原压缩字节、member 数量或容器参数相同。编码结果容许容器膨胀超过入站 10 MiB 读取上限，所有 encoder 完整成功后才提交。
- 出站头副本移除 Content-Length／Transfer-Encoding／Content-Encoding 的全部大小写变体，再写入唯一规范 Content-Encoding；无编码不写该头。长度由现有 transport 依据最终 bytes 自动生成，保留既有 HTTP/1 头名机制和画像顺序，不用未经抓包的新版头序替换。
- 诊断、日志、usage、缓存与 signature repair 持续使用逻辑正文；冻结编码链贯穿首次、401、signature 各阶段及换号发送，每次编码当前正文，不能复用首包压缩体。缓存不按压缩容器分裂，不新增上游 400／415 后改明文的回退重试。
- 入站拒绝没有账号相关副作用或上游请求。发送阶段本地编码失败只保证本次业务请求不提交，不回滚此前已有 admission／Hello／自动遥测。PreparedRequest 与 v3 sender 继续传最终原始 bytes，既有 origin／路径许可及内部接收上限不变。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 无编码／合理空列表／identity；仅 Accept-Encoding | 保留原业务及读体路径，不推断或新增压缩 |
| 已支持编码、重复头、有序叠加 | 解码后执行业务，按同一有效链发送 |
| 非法 token／不可转字符串／超过 32 片段 | 400 `invalid_request_error` |
| 未知合法编码／超过 4 个实际层 | 415 `invalid_request_error` |
| 损坏、截断、尾随内容、超支持窗口或扩展 | 400 `invalid_request_error`，不使用部分解码结果 |
| 压缩原字节或任一层结果超过 10 MiB | 413 `invalid_request_error`，先于账号副作用 |
| worker／本地编码异常 | 500 `api_error`，本次业务请求不提交 |
| 合法编码的非 JSON | 通用转发沿用原字节语义，count_tokens 保留原严格拒绝 |
| 上游返回 415 | 沿用原上游错误，不增加明文回退发送 |

错误体不回显原始编码值、正文、凭据或库内部错误；不靠不稳定库错误字符串细分窗口失败。

### 5. Scenarios and Examples

- 正常：入站 `Content-Encoding: gzip, br`，先 br 再 gzip 解码，完成身份与 CCH 后先 gzip 再 br 编码；最终长度对应双层压缩字节。
- 边界：raw-deflate 入站在 10 MiB 内，改写后按标准 zlib 包装略超 10 MiB，仍发送并使用实际长度；空项／identity 不增加压缩层。
- 错误：在 signature 修复前压缩 `final_body`，随后 JSON 修复失效；或重建头丢掉 Content-Encoding 后继续发旧压缩体。
- 正确：业务始终处理逻辑正文，在每次网络提交边界单独生成匹配的 wire body 和头；真实上游编码支持由响应决定，不用本地合成成功冒充真实推理。

### 6. Tests Required

- `request_body_codec::tests`：完整 token／多值／32 片段与 4 层边界、无编码存储保留、各 codec 与链顺序、raw 转标准 zlib、截断／尾随、每段校验、多 member／frame、窗口、原字节及各层精确大小、实际编码膨胀。
- `gateway_compressed_request_messages_match_plaintext`、`gateway_compressed_request_other_endpoints_match_plaintext`：实际 Gateway 比较 CC／API、stream 三态、过滤开关、各入口和编码的最终逻辑字节、身份／Session／CCH；通用二进制路径为合成样例。
- `gateway_compressed_request_rejections_have_no_account_side_effects`、`gateway_compressed_request_read_errors_and_count_json_boundaries`、`gateway_compressed_request_router_authentication_precedes_decoding`：实际入口错误状态／形状、零账号副作用及上游请求、鉴权／方法优先级和原无编码行为。
- `gateway_compressed_request_tcp_headers_and_near_limit`：真实 TCP 验证唯一 CE／CL、无旧 TE、实际 wire 长度与近上限膨胀；不以内部 Map 断言代替线上字节。
- `gateway_compressed_request_auth_and_account_retries`、`gateway_compressed_request_signature_stages_reencode_current_body`、`gateway_compressed_request_does_not_retry_unsupported_upstream_encoding`：401 双入口、429 换号、两阶段修复的本次正文及 CCH、不新增编码回退。
- `gateway_compressed_request_cache_and_local_intercepts_are_equivalent`：不同编码共用逻辑缓存、cache hit 无 attempt、本地 prefill／warmup／classifier 等价且不多发包。
- Rust 格式／全量／CCH 与差异检查通过；复用既有 transport 原始字节／证书／主机名回归。新增测试只证明本地合成 Gateway／TCP 与既有 transport 合同，不宣称新原生抓包、生产 v3 或真实账号推理验证。

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
- 池映射专用分支只在 `real_session_id != upstream_session_id`、即 body session 确实改变时覆盖或补入 `X-Claude-Code-Session-Id`。随后普通 CC 消息可按[有限对齐规则](#scenario-普通-cc-messages-session-header-对齐)更新已有非空头；探针和异常目标仍有明确豁免，不能无条件规范化 admitted/owner-hit。
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
- Gateway/Rewriter 单测覆盖：JSON/legacy `metadata.user_id.session_id` 改写、池实际改变 session 时的专用补入／覆盖优先级、普通已有头有限对齐及探针／异常目标豁免、自动 telemetry 的最终 body 来源、stateful cache key 使用真实 session、event_logging 递归只读映射和无 `events` 数组路径。
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

## Scenario: 普通 CC Messages Session header 对齐

### 1. Scope / Trigger

- Trigger：修改普通 CC Messages 出站 Session header、探针豁免或与池映射的先后关系时适用。
- 这是普通 CC 不一致输入的有限一致性规则，不重建 body 身份、设备、账号或会话；无新增 setting、存储状态或重试。

### 2. Signatures

- `is_session_header_alignment_probe(body: &serde_json::Value) -> bool` 使用原始请求体。
- `align_claude_code_session_header(headers: &mut HashMap<String, String>, path: &str, client_type: ClientType, original_body: &serde_json::Value, rewritten_body: &serde_json::Value)` 只修改出站头。
- 最终会话沿用 `extract_session_id_from_body` 的 JSON-string／legacy 合同；既有 `align_mapped_upstream_session_header` 先执行。

### 3. Contracts

- 仅精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 body 不属于豁免探针时进入普通对齐。
- 最终 body 可提取非空白 session、已有规范头 `X-Claude-Code-Session-Id` 非空白且不同、目标可安全且保真表示为 HTTP header 时，以最终 body 为准更新已有头；不补头、不 trim 写回、不新增 UUID 门槛。
- HTTP/1 会去掉头值边缘 SP／HTAB，因此目标 session 前后带这些字符时跳过普通对齐；全空白、LF／CR／NUL 或其它 HeaderValue 拒绝的目标也保留已有头。不要通过改 body 或提取器掩盖不一致。
- 探针四项同时满足才豁免：`max_tokens` 为整数 1、既有 stream 布尔解释不为 true、tools 缺失或为空数组、messages 恰好一条且 role=user。tools=null／异常类型、stream=true 不豁免；不依赖模型名、文本或拦截开关。合法同形业务请求也保守豁免。
- 既有 mapped 专用分支保持补入／覆盖能力，先处理真正的 body session 映射；新增探针或异常目标 gate 不撤销此前映射结果。API 既有规则、count_tokens 和其它路径不扩大。
- 原始 body 仍用于调度、sticky、RPM、并发、池与诊断；最终 body 只作为新增头的目标来源。不得额外 resolve、刷新 TTL、改变 Hello 去重、重序列化正文或增加 CCH 刷新；R2 根键清理开／关不影响嵌套会话来源。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 普通 CC 已有非空头与最终 body 会话不同 | 只改已有头，body 字节不因本规则改变 |
| 原本一致／缺头／空白头／无可用 body 会话 | 保持既有头状态，不补会话 |
| 非空目标前后 SP／HTAB 或不安全控制字符 | 跳过新增对齐，原 body 与原已有头保留 |
| 原始单 token 豁免探针，无实际映射 | 保留允许的差异 |
| 池已实际改变 body session，包括缺头探针 | 保留旧 mapped 补入／覆盖优先级 |
| 非精确路径／API | 新 helper 不改写，沿用各自既有规则 |

### 5. Scenarios and Examples

- 正常：原 header 为 A、最终 body 会话为 B，普通请求仅将已有 header 设为 B；不改变设备或 billing/CCH。
- 边界：173 最小 warmup 的差异继续保留；池将该探针实际映射到 C 时，旧 mapped 分支仍让 body/header 使用 C。
- 错误：将带前后空格的 body session 直接写进 HTTP 头，接收端会剥离空白，仍不一致；或先 trim 再改 body，扩大身份与 CCH 改写。
- 正确：对不能保真为头值的目标跳过新增普通分支；正常不带边缘空白的非 UUID 会话继续按原提取合同对齐。

### 6. Tests Required

- `gateway_session_header_alignment_ordinary_messages`：实际 Gateway 覆盖 JSON／legacy、三种 stream、清理开／关、头名大小写和原本一致／不一致；最终 CCH 保持有效，仅头不同时 body 字节相同。
- `gateway_session_header_alignment_input_and_path_boundaries`：缺失／空白／损坏会话、LF／CR／NUL、缺头／空头、API 补头和其它路径；断言实际上游最终头与 body。
- `gateway_session_header_alignment_probe_shape`：173／280 合成探针及 stream、tools、消息数、token 类型等反例；不能只测试 helper 或扩大 detector。
- `gateway_session_header_alignment_pool_precedence`：池关闭、admitted、owner_hit、mapped 与失败开放；resolve 次数、owner_only TTL、真实 sticky／诊断维度、Hello 去重。
- `gateway_session_header_alignment_preserves_sessions_with_edge_ows`：JSON／legacy × 清理开／关 × 前后 SP／HTAB，保留原 body 与已有头；正常及内部空白正例仍进入对齐。
- Rust 格式、全量与 CCH 回归通过；仅使用合成 loopback，不把它称为真实 Anthropic 推理或新抓包验证。

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
- 后台服务：`UsagePollerService::new(account_svc, interval: Duration, enabled: bool)`；`run()` 在 disabled 时直接返回
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
- 普通业务请求无论成功或 429 都不得调用 usage API。v3（`V3_RUNTIME_URL.trim()` 非空）关闭 `UsagePollerService`，历史 `auto_poll_usage=true` 也不触发查询，不改账号原开关；管理员手动 `/admin/accounts/:id/usage` 仍可查询。非 v3 保留 active OAuth＋`auto_poll_usage=true` 的定时刷新。
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
| v3 且历史 `auto_poll_usage=true` | poller 不运行，不访问 usage；业务响应被动合并保持 |
| 管理员手动刷新 / 非 v3 且 `auto_poll_usage=true` | 允许主动查询 usage，结果仍经过 rollover 合并 |
| 上游返回 401/403/429 | 维持现有 `AppError` 分类，不吞错误体 |

### 5. Good/Base/Bad Cases

- Good：usage 先返回 session/weekly all 两个 `scope: null` limit，后返回 Fable scoped limit；解析器跳过前两项并补出 `seven_day_fable`。
- Good：Fable 成功响应带 `7d_oi utilization/reset`，Gateway 收到响应头后异步写入 `seven_day_fable`，整个请求生命周期不访问 usage API。
- Good：旧 7d 为 99% 且 reset 已过期，下一次成功响应把 reset 推到下周但仍回 99%；合并层保存新 reset 并返回 0%，后续同 reset 的真实样本可继续更新。
- Base：非 v3 沿用账号开关轮询；v3 即使开关为 true 仍禁用 poller，手动查询可用。
- Base：只返回传统 `five_hour` / `seven_day`；保留已有 Fable 数据，不主动补查。
- Bad：直接假设 `limits[0]` 就是 Fable，或遇到第一个 `scope: null` 用 `?` 提前返回，导致真实 Fable 项被漏掉。
- Bad：在 Fable body EOF 或 429 后自动调用 usage API，绕过 `auto_poll_usage` 显式开关。
- Bad：只看新 reset 在未来就相信仍为 99%/100% 的成功样本，会把上一周期用量重新带入新周期。

### 6. Tests Required

- `service::oauth` 单测覆盖：前置 `scope: null` 项、Fable scoped 项、已有顶层 `seven_day_fable` 不覆盖、非 Fable scoped 项忽略。
- `service::gateway` 单测覆盖：5h/7d/7d_oi 完整解析、秒/毫秒 reset、缺失字段、非法数值和异常时间。
- `service::account` 单测覆盖：Allowed rollover 高位清零、已下降值采用、同周期后续更新、RejectedWindows 仅保留明确拒绝窗口高位及未观察字段不丢失。
- `service::gateway` 单测覆盖：429 按窗口 `status` 判定拒绝，显式 `allowed` 优先于高位 utilization，缺少 status 时兼容数值型 `surpassed-threshold`。
- `UsagePollerService` 使用真实 SQLite 账号与本地 TCP 代理，验证 disabled 零连接、enabled 保留轮询；账号 auto_poll_usage 不被改写。
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

## Scenario: 每账号 5h/7d 用量控制线

### 1. Scope / Trigger

- 修改账号用量限制、消息选号、sticky、账号新建/编辑页或 bench 创建账号兼容性时适用。
- 控制线约束网关消息分配，依据最近观测的真实额度百分比；与本地请求费用统计、RPM、Fable 专属额度分别处理。

### 2. Signatures

- `Account.five_hour_usage_limit_percent: i32`、`seven_day_usage_limit_percent: i32`，serde 缺失默认 0；SQLite/PostgreSQL 对应列为 `NOT NULL DEFAULT 0` 整数。
- `POST /admin/accounts` 可提交两个 JSON 整数字段，缺失默认为 0；`PUT /admin/accounts/{id}` 未提交的字段保留既有值。
- `AccountSelectionContext.usage_limits_enabled: bool` 仅在网关精确 `/v1/messages` 路径为 true，`disabled()` 为 false；普通窗口控制不依赖请求模型名。
- `AccountService::update_account_usage_limits(&self, account: &Account) -> Result<(), AppError>` 校验后调用 `AccountStore::update_usage_limits`，只写两个控制线和 `updated_at`。
- `account_usage_limit_reached(account)` 对普通 `five_hour`、`seven_day` 窗口进行判断；`select_account_with_selection_context` 在 sticky 与普通候选路径执行同一规则。

### 3. Contracts

- 两个控制线分别接受 0～100 的整数，0 关闭，1～100 为百分比；新账号、旧库升级及 bench 省略字段的创建请求均默认关闭，不新增全局设置或继承关系。
- 只有窗口用量为有限非负数字、`resets_at` 是未来 RFC3339 时间且 `utilization >= limit` 时命中；不使用调度评分的衰减百分比。未知、非法或过期窗口不据此拦截。
- OAuth 与 SetupToken 的普通窗口同样适用；不要照搬 Fable helper 的 OAuth-only 条件。
- sticky 达线时加入本轮排除并保留原绑定，只有替代账号实际承载后才重绑；无替代账号返回本地 `TooManyRequests`。普通候选先遵守 Token 范围和运行时排除，再过滤额度，最后执行既有 RPM/优先级/评分。
- 通用与 Fable 规则同时适用；混合达线不能回退到任何受限账号。普通账号阈值可以不同，错误信息不能把它们描述为同一全局阈值。
- 达线不改变 active/disabled 或写入 `rate_limit_reset_at`；窗口到期、调高或关闭上限后下次选号恢复，同时继续遵守其他窗口、Fable 与真实上游冷却。
- 判断点是选号读取到的账号快照；已分配、排队或执行中的请求不取消，不预扣/预测，不保证单次或并发请求严格不越线，不新增主动 usage 查询。
- count_tokens、管理接口、后台 poller/PrimePoller 和独立 CLI 不套用新控制线；不能宣称它限制全部账号用量来源。本地拦截保持原消息链路顺序。
- 服务创建、CLI 身份创建、更新均校验值域；动态更新必须在状态或配置写入前拒绝错误类型与越界值。同次提交 active/disabled 与控制线时仍须保存控制线，只写必要字段，不能把旧快照的凭据或状态整行回写。
- 账号表单所有初始化、新建、编辑、授权导入、保存入口必须同步；列表额度区显示已配置上限。控件为 0～100、步长 1，空值不能被转换成关闭限制的 0。
- bench 的现有创建载荷继续省略新字段，保留并发 4、RPM 50、session 池 4/owner_only 和 rewrite 等既有默认；后续关联、OAuth 刷新和进程指标导入不能清掉管理员设置的控制线。
- 双库 schema、幂等补列、INSERT/UPDATE bind 顺序、`ACCOUNT_COLS` 和 row mapping 必须同步；PostgreSQL JSONB 与时间列通过文本投影适配 SQLx Any，具体类型约束见 [Settings & Database](./settings-database.md#account-字段同步)。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 账号 A 的 5h=80/7d=60，任一窗口恰好达线 | 跳过 A；可用替代账号仍按既有范围和评分选择 |
| 两个窗口分别为 79.9%/59.9% | 允许 A，不提前预留缓冲 |
| 0 / 100 控制线 | 0 不检查该窗口；100 在 99.9% 允许、100% 命中 |
| 已达线账号无可用替代 | 本地 429，保留原 sticky，不调用上游 |
| 窗口未知、无效或过期 | 不按该窗口拦截；其他有效窗口仍可拦截 |
| 创建/更新字段为负数或大于 100 | BadRequest，旧数据不变 |
| 字段为字符串、布尔、小数或 null | 创建反序列化拒绝，动态更新 BadRequest，不静默忽略 |
| 仅更新一个控制线或不提交两个字段 | 另一个值或两个既有值保留 |
| 状态快捷操作同时提交控制线 | 状态与控制线都生效，保留新凭据和其他策略 |
| 两次迁移或刷新凭据/指标 | 非零控制线保留 |

### 5. Scenarios and Examples

- 正常：A 的上限为 80/60，B 为 90/70；A 的 5h 观测为 85% 后不能继续承载消息，同样用量的 B 仍可使用。
- 基础/边界：bench 新建账号省略字段，两个值均为 0；管理员在 cc2api 编辑页设置 80/60，后续凭据同步不会恢复为 0。
- 错误：直接设置 `rate_limit_reset_at` 表示管理员控制线，或状态切换后把旧 Account 整行更新，会延迟配置恢复或覆盖新凭据。
- 正确：每次消息选号只读窗口与账号阈值；状态与控制线组合更新走独立控制线 SQL，保持其余字段和真实上游冷却。

### 6. Tests Required

- `tests/account_scheduler_test.rs::usage_limits_*`：两窗口/两类账号、临界值、独立阈值、Token 范围、sticky 保留与重绑、全部达线、关闭/调高/重置恢复、脏窗口、Fable 叠加和服务校验。
- `handler::router::tests::usage_limits_*`：bench 旧载荷默认、局部更新、错误类型/范围无部分写入、状态与控制线组合保存。
- `gateway::tests::usage_limits_gateway_filters_messages_and_preserves_count_tokens`：真实本地上游账号选择、达线无上游发送、count_tokens 兼容与调高热生效。
- `tests/account_store_timestamp_test.rs::usage_limits_*`：SQLite/PostgreSQL 旧库缺列升级、重复迁移、创建/更新/详情/分页/调度字段往返，以及凭据/指标/状态变化后独立控制线写入不覆盖其它字段。
- 管理页构建及真实输入保存/回显/0 关闭/非法输入不提交/新建重置；必需 `cargo fmt --check`、完整 `cargo test --locked`、`npm run build`。

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
- `resolve_upstream_token` 只允许临时刷新失败时使用仍有效 AT 的兼容 fallback；永久凭据错误不得回退。管理端 resolve 不允许返回不满足最小有效期的旧快照。
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
| refresh token 缺失 | 更新 auth error，返回 `PermanentCredential` |
| refresh 返回 `invalid_grant` | 返回 `PermanentCredential`，不使用旧 RT/AT 伪装成功 |
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

## Scenario: OAuth Token 预解析永久凭据错误停用与切号

### 1. Scope / Trigger

- 修改 OAuth token endpoint 错误分类、`AccountService::resolve_upstream_token`、Gateway 请求转发前 Token 预解析，或账号认证失败停用逻辑时适用。
- 目标是在账号级凭据已确定永久失效时停用当前账号并在同一请求内切号，同时避免 OAuth endpoint 临时故障触发批量误停或逐账号放大。

### 2. Signatures

```rust
AppError::PermanentCredential(String)

oauth::refresh_oauth_token_at(
    refresh_token: &str,
    proxy_url: &str,
    token_url: &str,
) -> Result<RefreshedOAuthTokens, AppError>

AccountService::resolve_upstream_token(id: i64) -> Result<String, AppError>
AccountStore::disable_for_auth_failure(id: i64, reason: &str) -> Result<(), AppError>
AccountService::disable_for_auth_failure_if_current(expected: &Account, reason: &str) -> Result<(), AppError>
```

- Gateway 适用入口为 `/v1/messages` 与 `/v1/messages/count_tokens`。
- `PermanentCredential` 的外部 HTTP 映射保持 503；所有候选耗尽时返回 Anthropic `api_error` 形状的通用 503。

### 3. Contracts

- OAuth 非 2xx 响应只读取最多 4 KiB 错误体，并只接受最长 64 字符、由 ASCII 字母数字、`_`、`-` 组成的短 `error` 码。不得记录 `error_description`、完整响应正文、AT、RT、Authorization、Cookie 或代理密码。
- 仅客户端错误且状态不是 429、短错误码为 `invalid_grant` 时返回 `PermanentCredential`。429、5xx、网络/超时、响应解析失败和其他错误码保持临时错误；临时 HTTP 状态优先于响应体中的 `invalid_grant` 文本。
- OAuth 账号缺少 refresh token 时必须在有效 AT 快路径之前返回 `PermanentCredential`；有效 AT 不能掩盖已无法续期的账号状态。
- 永久凭据错误必须保留到 Gateway，不得包装回普通 `ServiceUnavailable`，也不得使用仍有效旧 AT fallback。临时错误可继续复用尚未过期的 AT，并且不得切换到其他账号放大 token endpoint 故障。
- 只有 Gateway 请求调度路径负责停用账号；管理端 resolve、usage、telemetry 和后台任务可观察该错误，但不得仅因一次解析调用自行修改账号状态。
- Gateway 收到 OAuth `PermanentCredential` 后调用 `disable_for_auth_failure_if_current`，按原 AT/RT 且仍为 active OAuth 的条件写入。实际命中时原子写入 `status=disabled`、相同的 `auth_error` / `disable_reason` 并清空两项限流时间；已换凭据或人工停用时忽略旧回包，SQL 失败仍向上返回。无条件 `disable_for_auth_failure` 保留给既有 SetupToken 路径。
- 停用成功后把账号加入本轮 `exclude_ids`；`/v1/messages` 还必须显式释放当前 slot，再继续账号选择。sticky 选择必须服从同一排除集合，同一请求内每个永久失效账号最多探测一次。
- 永久凭据排除必须使用独立状态判断，并在候选耗尽时优先于历史 429 返回通用 503；不得改变普通 401 恢复失败与历史 429 的既有优先级。

### 4. Validation & Error Matrix

| 条件 | 分类 | Gateway 行为 |
|------|------|--------------|
| HTTP 400，`error=invalid_grant` | `PermanentCredential` | 原子停用、排除并切号 |
| refresh token 缺失，即使 AT 仍有效 | `PermanentCredential` | 不调用 token endpoint，原子停用并切号 |
| HTTP 429，即使正文含 `invalid_grant` | 临时错误 | 不停用、不跨账号重试；有效 AT 可 fallback |
| HTTP 5xx，即使正文含 `invalid_grant` | 临时错误 | 不停用；有效 AT 可 fallback |
| 网络、超时或响应解析失败 | 临时错误 | 不停用；无有效 AT 时保持当前失败语义 |
| 首账号永久失效、后续账号可用 | 永久错误已隔离 | 当前请求由后续账号完成，不向客户端泄漏前一账号错误 |
| 所有候选永久失效 | 永久错误已隔离 | 返回通用 Anthropic 503，每个账号最多探测一次 |
| 先收到 429、后遇永久凭据错误 | 永久错误已隔离 | 返回通用 503，不返回旧 429 |
| 账号停用 SQL 失败 | 存储失败 | 立即返回错误，不继续切号 |

### 5. Good/Base/Bad Cases

- Good：高优先级 OAuth 账号刷新返回 `invalid_grant`，Gateway 原子停用并排除该账号，释放 slot 后由第二账号完成原请求；后续请求不再调度失效账号。
- Base：token endpoint 返回 503，旧 AT 仍有效；请求继续使用旧 AT，账号保持 active，备用账号不参与本次请求。
- Bad：根据完整错误字符串包含 `invalid_grant` 决定停号；429/5xx 代理错误可能夹带该文本，造成批量误停。
- Bad：先检查 AT 有效期再检查 RT 是否存在；缺失 RT 的历史账号会继续被调度，直到 AT 过期后才暴露故障。
- Bad：永久错误切号后仍优先返回之前缓存的 429，客户端会看到错误的失败原因，且无法确认永久失效账号已被隔离。

### 6. Tests Required

- OAuth 分类单测覆盖：标准 400 `invalid_grant`、错误描述脱敏、429/5xx 携带 `invalid_grant` 仍为临时错误、未知错误码保持临时错误。
- AccountService 单测覆盖：有效 AT 不能绕过缺失 RT、永久错误不 fallback、临时错误仍可 fallback、管理端凭据快照保留永久错误类别。
- Gateway 回归覆盖：普通 `/v1/messages`、sticky、`count_tokens` 的停用切号；缺失 RT；所有账号永久失效；先 429 后永久失效；5xx 和网络失败不误停、不切号。
- Store 测试断言 `disable_for_auth_failure` 同时写入 disabled、两类原因并清空两个限流时间。
- 完整验证至少运行 `cargo fmt --check`、OAuth/账号/Gateway 定向测试、`cargo test` 和双仓 `git diff --check`。

### 7. Wrong vs Correct

#### Wrong

```rust
let token = account_svc.resolve_upstream_token(account.id).await?;
```

该写法把永久凭据错误直接返回给客户端，账号仍保持 active 并在后续请求中反复入选。

#### Correct

```rust
match account_svc.resolve_upstream_token(account.id).await {
    Ok(token) => token,
    Err(AppError::PermanentCredential(reason)) => {
        account_svc
            .disable_for_auth_failure_if_current(&account, &reason)
            .await?;
        exclude_ids.push(account.id);
        drop(slot_guard);
        continue;
    }
    Err(error) => return Err(error),
}
```

实际永久错误停用后切号；旧凭据快照已过期时只排除本请求中的旧候选，不能停用新登录凭据。临时错误沿用原失败或有效 AT fallback 语义。

## Scenario: 有效上游 Session 首次 Hello 代理探测

### 1. Scope / Trigger

- Trigger：修改 Claude Code `/v1/messages` 首次连通性检查、账号代理网络路径、上游 Session 池解析、Session 去重、CacheStore/Redis singleflight、严格模式或对应 Settings 时适用。
- 目标：新的有效上游 Session 第一次准备承载上游请求时，通过最终选中账号的 `proxy_url` 匿名探测 Anthropic Hello；同一活跃上游 Session、账号、有效画像和代理路径只探测一次。
- 公开 `GET/HEAD /api/hello` 仍是无状态本地健康端点，不进入账号选择或代理探测；完整 wire 画像见 `../protocol/claude-code-profile-upgrade.md`。

### 2. Signatures

- 服务入口：`SessionHelloProbeService::ensure_ready(account, real_session_id, upstream_session_id, config).await -> SessionHelloProbeDecision`。
- 决策：`Proceed`、`BlockFailure`、`BlockTimeout`、`BlockUnavailable`。
- CacheStore：`get_session_hello_probe_state(key, success_ttl)`、`set_session_hello_probe_state(key, state, ttl)`，并复用 owner 语义的 `acquire_lock/release_lock`。
- 状态 key：`session_hello_probe:v2:<account_id>:<profile_key>:<sha256(upstream_session_id)>:<sha256(proxy_url)>`，singleflight 使用相同画像维度。
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
- 探测请求固定为匿名 `HEAD https://api.anthropic.com/api/hello`，`User-Agent` 来自请求账号副本的有效画像：280 为 `Bun/1.4.3`、260/257 为 `Bun/1.4.1`、220 为 `Bun/1.4.0`；其余 header 为 `Accept: */*`、`Accept-Encoding: gzip, deflate, br, zstd`、`Connection: keep-alive`。不得添加 query、body、Authorization、Cookie、billing header 或用户数据。
- 非空 `Account.proxy_url` 必须由 `tlsfp::get_request_client` 内部通过 `reqwest::Proxy::all` 校验并应用；客户端创建失败时返回错误，无效代理不得静默直连。空代理允许直连。
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
let client = make_request_client(&account.proxy_url)
    .unwrap_or_else(|_| reqwest::Client::new());
let response = client.head(HELLO_URL).send().await?;
account_svc.acquire_account_rpm(&account, sticky, session_hash).await?;
```

代理或 TLS 客户端构建失败时退回默认客户端会绕过账号代理，而且探测后再次 admission 会把一轮业务请求计成两次 RPM。

#### Correct

```rust
let state = match get_request_client(&account.proxy_url) {
    Ok(client) => run_anonymous_head(client, config.timeout).await,
    Err(_) => SessionHelloProbeState::Failure,
};
```

Gateway 在既有 admission 后调用 `ensure_ready`；共享 client factory 负责代理失败关闭，服务再执行匿名 HEAD、状态缓存和 singleflight，不执行第二次 RPM admission。

## Scenario: Claude Code 状态分类旁路与归因补齐

### 1. Scope / Trigger

- Trigger：修改 Claude Code 后台 Agent 状态分类请求的识别、请求体改写、模拟响应、请求日志、账号代理或对应 Settings 时适用。
- 目标：保留 Fable 5.1 `cli-bg` 请求的窄范围模拟能力，并为 Claude Code 非 Haiku 状态分类请求提供默认关闭的 billing/CCH 与官方身份块补齐；普通 `/v1/messages`、Haiku、旧 Auto Mode classifier 和账号调度行为必须保持不变。

### 2. Signatures

- setting：`intercept_cli_bg_status_classifier_mode=passthrough|mock`，默认 `passthrough`。
- setting：`intercept_cli_bg_status_classifier_identity_injection_enabled=true|false`，默认 `false`。
- runtime config：`CliBgStatusClassifierConfig { mode, identity_injection_enabled }`。
- 窄 detector：`is_cli_bg_status_classifier_request(path, headers, body, client_type) -> bool`。
- 通用 detector：`detect_claude_code_status_classifier_request(path, headers, body, client_type) -> Option<CliStatusClassifierMatch>`。
- identity-only 改写：`Rewriter::rewrite_claude_code_identity_only(body, account, upstream_session_rewrite) -> Vec<u8>`。
- 归因补齐：`Rewriter::rewrite_claude_code_status_classifier_attribution(body, account, upstream_session_rewrite) -> Vec<u8>`。
- TLS 客户端：`tlsfp::get_request_client(proxy_url) -> Result<reqwest::Client, reqwest::Error>`。
- mock 外层返回 Anthropic Message envelope，`content[0].text` 是可二次解析的 `state/detail/tempo/needs/output` JSON。

### 3. Contracts

- 窄 detector 必须同时匹配精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 `x-app=cli-bg`、精确 `claude-fable-5-1`、`stream=false`、`max_tokens=3072`、唯一 ephemeral classifier system text block 和唯一 user 状态文本。只有该 detector 可以选择 `mock`；Fable 5、`[1m]`、普通主请求和旧 XML classifier 不得进入模拟链路。
- 通用 detector 必须匹配精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 `x-app=cli|cli-bg`、`stream` 缺失或为 `false`、非空模型、唯一 classifier block 和唯一 user 状态文本。system 只允许至多一个严格 billing block、至多一个精确官方身份块和唯一 ephemeral classifier block；未知、重复或形状异常的 block 必须拒绝。通用 detector 不得硬编码模型名或 `max_tokens`。
- 归因补齐仅在 `mode=passthrough`、`identity_injection_enabled=true`、通用 detector 命中且模型不是 Haiku 时执行。开关关闭时必须完整保留既有链路；Haiku 在开关切换前后的上游请求体必须一致，也不得新增身份块。
- billing 缺失时使用共享 Claude Code API billing builder 插入 billing 并计算有效 CCH；已有 billing 且包含 CCH 时按最终请求体刷新 CCH；已有 billing 但没有 CCH 时保留原 block，不擅自增加 CCH。最终 system 顺序固定为 billing、identity、classifier，CCH 只能基于最终序列化正文计算。
- 归因补齐只允许账号 metadata、upstream session identity、billing、identity 和 CCH 变化，不运行 expansion、缓存断点、TTL、thinking、字段顺序或其它通用正文改写；结构异常时失败开放并返回原正文。
- 独立的 `message_top_field_filter_enabled` 默认开启，三条 Messages 转发分支在本函数前统一清理固定根键，实际删除后在最终输出刷新已有唯一 CCH；这是旁路合同的有限例外，不扩展 detector 或其它通用改写。此处失败开放的“原正文”指传入函数的正文；无删除时仍保持原字节。具体范围、设置与测试见 [Messages 固定顶层字段清理开关](../protocol/claude-code-profile-upgrade.md#scenario-messages-固定顶层字段清理开关)。
- 账号 `allow_fast_mode=false` 的 Fast 策略在三条真实转发分支汇合后统一执行：只删除根级精确 `speed: "fast"`，并继续过滤完整 Fast beta；实际删除后刷新已有唯一合法 CCH，包含 Strip 旁路。该策略独立于根键清理和身份注入开关，不运行其它通用正文改写；允许或无删除时保留原字节行为。换号从公共原文重新按当前账号判断，不能沿用前次删除结果。详见 [Fast 账号控制](../protocol/claude-code-profile-upgrade.md#scenario-claude-fast-mode-账号级透传控制)。
- 窄 detector 命中 `passthrough` 且未执行归因补齐时，继续使用 identity-only 改写。所有 passthrough 请求仍走账号选择、sticky、RPM/concurrency、OAuth、2.1.257 header、账号代理/TLS、Session Hello、401、signature/429 retry 和响应透传；不得因为识别成 classifier 而跳过 Session Hello。
- classifier 命中后全文请求、429 请求和非流式响应捕获全部禁用，只保留尺寸、短 hash、重试次数与 `proxy_configured` 等脱敏摘要。`mock` 必须在 session hash、账号选择、RPM 和并发槽之前返回，不访问上游或消耗账号额度。
- mock 分类优先级固定为：API/auth/infra 错误 -> blocked；Agent 明确自动复查/继续执行 -> working；无自动复查的用户门槛 -> blocked；明确 failed/done；最后回退 `Current state`，未知值保守返回 working。
- 非空代理由共享 TLS client factory 强制解析和应用；代理或客户端构建失败必须向调用方返回错误，所有 gateway、OAuth、Hello、Prime 和 telemetry 调用点都不得自行退回直连客户端。错误日志不得包含代理 URL 或其中的凭据。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|------|------|
| 窄 detector 命中 + `mock` | 本地 HTTP 200 Message envelope，不进入账号和上游链路 |
| 窄 detector 命中 + `passthrough` + 注入关闭 | identity-only 改写后经账号代理转发，保留 Session Hello，禁用全文捕获 |
| 通用 detector 命中 + 注入开启 + 非 Haiku | 补齐 billing/identity，按 billing 原状态计算或刷新 CCH，经账号代理转发 |
| 通用 detector 命中 + 注入开启 + Haiku | 使用开关开启前的既有请求链路，上游正文不得因本开关变化 |
| 任一 detector 条件不满足 | 使用普通请求链路和管理员现有改写设置 |
| 已有 billing+CCH | 保留 billing 内容并按最终正文刷新 CCH |
| 已有 billing 但无 CCH | 保留原 billing，不自动增加 CCH |
| `Awaiting your go` 且声明 `Next check` | working，Agent 仍持有下一步 |
| 需要用户选择修复、环境或提交位置且无自动复查 | blocked |
| API/auth/infra 错误同时声明重试或复查 | blocked，硬错误优先 |
| 非空代理无法解析或客户端构建失败 | 返回受控错误，不连接目标上游，不退回直连 |

### 5. Good/Base/Bad Cases

- Good：非 Haiku 通用 classifier 在注入开启时，代理收到 billing、精确官方身份块、classifier 三段有序 system，且 CCH 对最终请求体有效。
- Good：Haiku classifier 在开关开启和关闭时，代理收到的请求体逐字节一致；已有身份块不会重复插入。
- Good：上游地址设为不可达域名，账号配置本地 mock HTTP proxy；passthrough 请求只有经过该代理才能获得 200。
- Good：全文非流/429 日志全局开启时，classifier 仍只写安全摘要；其它普通请求继续遵守管理员日志设置。
- Base：mode 缺失时默认 `passthrough`，注入开关缺失时默认 `false`；旧数据库只补缺失 key，管理员已有合法值不被覆盖。
- Bad：用通用 detector 扩大 `mock` 命中范围，会把未经验证的模型或 `x-app=cli` 请求本地短路。
- Bad：classifier 命中后跳过 Session Hello，会让默认关闭的注入开关也改变既有请求行为。
- Bad：在 billing/identity/classifier 完成排序前计算 CCH，会生成与最终上游正文不一致的 attestation。
- Bad：代理解析失败后创建默认 `reqwest::Client`，会从宿主机直连并暴露与账号不一致的网络/TLS 特征。

### 6. Tests Required

- 窄 detector 覆盖完整 Fable 5.1 正例，以及 path、UA、x-app、model、stream、max_tokens、system/user marker、Fable 5、`[1m]` 和旧 classifier 负例。
- 通用 detector 覆盖 Fable、Opus、Sonnet 与真实 Haiku 形状正例，以及 stream、x-app、未知 system block、重复 billing/identity/classifier 和缺失 marker 负例。
- 归因改写测试覆盖 billing 缺失、已有 billing+CCH、已有 billing 无 CCH、system 顺序、CCH 有效性、已有身份不重复和重复执行幂等。
- Gateway 代理测试覆盖注入开关关闭/开启、Haiku 与基线正文一致、已有身份不重复、Session Hello 仍执行、窄 mock 本地返回和非法代理失败关闭。
- mock 测试覆盖四状态 schema、API/auth 硬阻塞、自动复查优先级、用户门槛、可选追加任务和未知状态回退。
- TLS client factory 覆盖相同代理复用、不同代理隔离、关闭连接池和非法代理不缓存直连客户端。
- Settings 测试覆盖默认值、旧库迁移、GET/PUT 校验、mode 与注入开关独立热刷新；前端构建必须验证两个控件均可持久化。
- 完整验证运行 `cargo fmt --check`、classifier/settings/CCH 定向测试、`cargo test`、前端 `npm run build`、`git diff --check` 和敏感内容扫描。

### 7. Wrong vs Correct

#### Wrong

```rust
if !is_cli_status_classifier {
    if let Some(real_session_id) =
        session_hello_probe_session_id(&path, client_type, &body_map)
    {
        // 执行既有 Session Hello 链路。
    }
}
```

分类识别只应选择日志、模拟或正文改写策略；用它改变既有 Session Hello 条件，会使默认关闭的注入开关也产生行为回归。

#### Correct

```rust
if let Some(real_session_id) = session_hello_probe_session_id(&path, client_type, &body_map) {
    // 执行既有 Session Hello 链路。
}
```

Session Hello 继续由原有 probe 条件决定；classifier 配置只在同一既有代理链路内选择 mock、identity-only 或归因补齐。

#### Wrong

```rust
let client = reqwest::Proxy::all(proxy_url)
    .ok()
    .and_then(|proxy| builder.proxy(proxy).build().ok())
    .unwrap_or_else(reqwest::Client::new);
```

代理配置或指纹客户端构建失败会被吞掉，随后从宿主机直连；同一辅助请求还可能进入通用正文和全文日志链路。

#### Correct

```rust
let client = get_request_client(&account.proxy_url)
    .map_err(|_| AppError::BadGateway("upstream request client unavailable".into()))?;
```

共享 client factory 只缓存成功构建的客户端，非空代理失败立即向上传播；Gateway 对 classifier 单独选择正文改写和 summary-only 日志策略。

## Scenario: v3 重授权凭据导入与迟到回包保护

### 1. Scope / Trigger

- 修改 CLI 重授权导入、OAuth 回执/锁、登录维护租约，或刷新/401 的认证状态写入时适用。bench 的暂存与恢复流程见 [固定账号环境](../../vibecoding-bench/backend/account-runtime-v3.md#scenario-v3-关联重授权提交与恢复)。

### 2. Signatures

```text
POST /admin/accounts/:id/oauth-credentials/import
GET  /admin/accounts/:id/oauth-credentials/import/:operation_id
OAuthCredentialImport {
  operation_id: String, owner: String, generation: String, email: String,
  account_uuid: Option<String>, organization_uuid: Option<String>,
  access_token: String, refresh_token: String, expires_at: i64
}
oauth_credential_imports(
  operation_id TEXT PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  request_hash TEXT NOT NULL, created_at TEXT NOT NULL)
AccountService::import_oauth_credentials(id: i64, input: &OAuthCredentialImport)
  -> Result<OAuthCredentialSnapshot, AppError>
AccountService::oauth_import_status(id: i64, operation_id: &str)
  -> Result<Option<OAuthCredentialSnapshot>, AppError>
AccountService::disable_oauth_for_failed_token(id: i64, failed_access_token: &str, reason: &str)
  -> Result<bool, AppError>
RuntimeGate::begin_oauth_import(owner: &str, generation: &str)
  -> Result<OAuthImportPermit, AppError>
```

### 3. Contracts

- 两路导入/对账要求管理 Bearer 和 `x-v3-service-token`；`V3_RUNTIME_URL` 非空，`V3_INTERNAL_TOKEN` 至少 32 字节且恒时比较。浏览器不持内部秘密，不公开凭据快照。
- DTO 拒绝未知字段。操作 ID 为 32 位十六进制；bench 生成小写 UUID hex。邮箱非空且最多 320 字节；AT/RT 非空、各不超过 16384 字节且只含非空白可见 ASCII。新提交有效期为 UTC 毫秒，至少剩余 60 秒。
- 原账号须为 OAuth；邮箱、已有非空 UUID/组织按 trim/ASCII 忽略大小写匹配。原 UUID/组织已存在时，新值不可缺失。接口不修改设备、画像、代理或身份字段。
- 复用 `oauth:refresh:account:{id}` 的 Memory/Redis 锁：TTL 30 秒、500ms 间隔最多 20 次等待。锁内重读回执/账号，首次导入要求未过期、claimed、exclusive 的同代 `login:` 租约，active/importing 均为 0。
- 凭据、回执与认证恢复同事务写入；按原 AT/RT、状态、停用原因、邮箱及 UUID/组织做条件更新。冲突回滚回执。SQLite/PostgreSQL 共同幂等建表，回执只存请求 SHA256 与元数据，不额外保存令牌。
- 同操作、同账号、同载荷返回当前权威快照，不重写首次 RT；载荷/账号冲突拒绝。提交响应包含 `imported:true`、账号/操作 ID、AT/RT/毫秒有效期。对账无回执返回 `imported:false` 与账号/操作 ID；导入仍在途时返回不可确认错误，不能伪报未提交。
- 导入清旧 auth_error。仅 disabled 且 auth_error 等于 disable_reason、原因属于已有 OAuth 401、缺 RT 或已分类的非 429 客户端 `invalid_grant` 时恢复 active。支持已有 `permanent credential failure: ` 前缀；人工/其他停用、限流及未知配置保持，不调用会清限流的通用 enable。
- import permit 固定在途占用，release 在 importing 非 0 时拒绝。`fence` 仅同代排他 `login:` 租约使用，将 phase 写为 reconcile、expires_at=0，撤销后续导入；已在途事务仍须对账收口。
- 所有 OAuth 刷新成功/失败/缺 RT 写入按调用时 AT/RT 条件更新；失配丢弃旧结果并重读。gateway/count_tokens/prime 的 401 按实际失败 AT 重读，再以当前 AT/RT 和 active OAuth 条件停用，不能用刷新前的账号副本停用刷新后的结果。prime 的失败 AT 仅内存传递，不进日志/回执；转发与重试协议保持。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 缺管理或内部服务证明、非 v3 | 401 |
| DTO/令牌/操作 ID/身份/有效期不合法 | 拒绝；service 的 BadRequest 为 400，JSON 结构错误由 Axum 拒绝 |
| 登录租约不存在 | 400，不导入 |
| 非 claimed 同代登录租约、未排空、锁等待超时、条件写入失配 | 503，不释放维护门禁 |
| 同 ID 不同载荷、对账账号冲突 | 400，原凭据/回执保持 |
| 回执已提交且租约已失效 | 只读返回当前快照，不再次导入 |
| 导入未知或仍在途 | 503，不能返回 imported:false |
| 迟到刷新/401，或已人工停用 | 条件写入不命中，保持新凭据/状态 |

### 5. Scenarios and Examples

- 正常：原登录租约导入一次，再查询同操作回执；只更新原账号，设备与限流不变。
- 基础：人工停用账号仍可修复凭据，但保持 disabled；认证恢复与养号开关、额度门禁分开。
- 错误用法：响应丢失后生成新操作或再次覆盖第一次 RT。正确处理：保留原操作/载荷，查询回执后使用当前权威快照。
- 错误用法：锁 TTL 足以防旧回包，或按旧账号 ID 无条件停用。正确处理：OAuth 锁加 AT/RT 条件写入；401 使用实际失败令牌。
- 错误用法：取消时先 release 再查询。正确处理：先 fence，等待在途提交确定，清理暂存后才 release。

### 6. Tests Required

- `login_import_*`：只恢复认证停用、保留限流/身份；UUID/组织缺失冲突；条件更新回滚回执；同操作返回进一步轮换后的 RT。
- gateway/prime 的迟到 OAuth 401 回归：新凭据保持 active；人工停用不被旧请求覆盖；普通刷新后再次 401 仍按既有规则停用。
- `login_import_fences_late_calls_and_prevents_early_release`：在途 pin、fence 后拒新导入、释放前 API 关闭、确认后放行。
- `cargo fmt --check && cargo test --locked`；SQLite 实测及 PostgreSQL SQL 兼容检查。隔离临时 DSN 未配置时明确记录已有 PostgreSQL 测试 skipped/ignored。

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

画像选择配置通过 `reload_profile_selection_config` 将 mode/default 一次性读入同一把 `RwLock`。请求通过原始 UA 准入后、读取 body 前冻结选择；客户端模式的重试和异步回调复用该画像，不能随 reload 串版。完整配置、账号副本及遥测/缓存契约见 [按客户端 UA 选择请求画像](../protocol/claude-code-profile-upgrade.md#scenario-按客户端-ua-选择请求画像)。

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

## Scenario: v3 CLI 本地身份来源导入

### 1. Scope / Trigger

- 修改 `POST /admin/accounts` 的 `cli_identity`、来源白名单或首次 CLI 账号同步时适用。固定 HOME 读取及两端同步见 [v3 身份契约](../../vibecoding-bench/backend/account-runtime-v3.md#scenario-v3-原生-tls-账号身份与同步)。

### 2. Signatures

```text
CliIdentityImport {device_id, environment_id, source, canonical_env, canonical_prompt}
CliIdentityImport::has_confirmed_source() -> bool
AccountService::create_cli_account(&mut Account) -> Result<(), AppError>
```

### 3. Contracts

- 仅在既有管理 Bearer 与有效 `x-v3-service-token` 校验后导入；普通管理密码不能代替内部服务证明。
- 原 `cli:/v1/messages:metadata.user_id.device_id` 来源继续支持。新增 `cli:2.1.293:config.userID` 仅接受 canonical_env.version / version_base 同为 `2.1.293`，依据独立官方 CLI 禁网请求实证，不开放任意版本或配置字段。
- 服务层继续校验设备 ID、Linux 运行环境和 prompt 环境并直接保存已确认身份，不随机生成替代设备；已有账号通过绑定流程检查，不能借首次导入覆盖旧设备。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 合法内部证明、环境与已验证来源 | 按原设备创建账号 |
| 缺内部证明／未知 source／配置来源版本不匹配 | 401，不创建账号 |
| 设备或运行环境不完整 | 400，不创建账号 |

### 5. Scenarios and Examples

- 正常：bench 读取 2.1.293 固定 HOME 的有效 userID，并以准确来源创建账号；保持同一设备。
- 基础：旧正式请求观察仍走原来源，未验证版本不得假称已验证本地映射。
- 错误用法：只放开 source 字符串而不绑定版本。正确处理：白名单来源与 version / version_base 同时匹配，并保留内部鉴权及服务层校验。

### 6. Tests Required

- `cli_identity_sources_require_verified_version`：精确版本通过，版本／version_base 不匹配、未来版本和 machineID 来源拒绝；旧观察兼容。
- `cli_identity_import_requires_internal_service_proof`：只有管理 Bearer 的 HTTP 请求返回 401。
- v3 隔离同步／重授权堆栈：正式同步请求创建后核对实际 SQLite 的 device_id 与持久 userID 相等，再验证重授权凭据和原账号保持；不访问真实 OAuth／模型。
