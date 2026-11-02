# 已交接的普通 Session 对齐规范

来源：`.trellis/spec/cc2api/backend/service-architecture.md`；SHA256：`7072a8a0ab2245134a965557a01f77641832febce7745ccba6eb9375d4b34c71`。以下为该场景完整原文，R3不得回退。

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
