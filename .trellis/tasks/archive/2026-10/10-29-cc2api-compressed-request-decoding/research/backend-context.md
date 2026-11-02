# 本项相关规范原文摘录

来源：`.trellis/spec/cc2api/backend/service-architecture.md`；SHA256：`7072a8a0ab2245134a965557a01f77641832febce7745ccba6eb9375d4b34c71`。仅作有界上下文；不改变原规范。

## 原文 17—37 行

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


## 原文 53—70 行

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

## 原文 162—210 行

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


## 原文 800—814 行

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
