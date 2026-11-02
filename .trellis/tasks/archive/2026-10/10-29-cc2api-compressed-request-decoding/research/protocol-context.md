# 本项相关规范原文摘录

来源：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`；SHA256：`ebfe84883a949f912a845712ee0ee9adc28710a2397cbb1417a536fcf849184a`。仅作有界上下文；不改变原规范。

## 原文 183—219 行

CCH 契约：

- 占位化、初始封口与重试刷新只定位唯一受管理的根级 `system` billing：支持字符串和直接
  `type=text` 块，首个非空白位置须是 billing attribution 行，可跟多行普通上下文。普通文档后续引用、
  messages、tools、metadata 或嵌套 system 中的 CCH 字面量不得被这三步改写。
- attribution 行按独立分号字段识别唯一合法五位 hex CCH；保留既有入口值、附加归因键和原始顺序，
  不要求恰好三个字段或固定字段顺序。`note=cch=12345` 和 `xcch=fedcb` 不构成 CCH 字段。
- 在最终原始字节上只回填该五位值；解码字符串偏移不能直接当作 JSON 字节偏移。目标缺失、非法、
  重复或无法可靠回填时保持 CCH 处理函数的输入，不回退全文搜索、不新增合并或拒绝策略。
  前置占位化继续沿用 cache_control 键存在即跳过的既有规则，包括 null。
- seed 不是默认可变项；升级时先用旧 seed 复算，不命中再尝试找 seed。
- `2.1.156`、`2.1.169`、`2.1.172`、`2.1.173`、`2.1.185`、`2.1.187`、
  `2.1.195`、`2.1.197`、`2.1.220`、`2.1.257`、`2.1.260`、`2.1.280`、`2.1.293` 使用 seed
  `0x4D659218E32A3268`；不能因版本号变化直接更换 seed。
- `2.1.169`：在最终 body 字节上把真实 `cch=<5hex>` 替回 `cch=00000` 后计算，保留完整 body。
- `2.1.172`：在最终 body 字节上替回 `cch=00000` 后，再做 top-level 规范化：
  - `model` 字段保留 key 和空字符串值，排除原模型值。
  - 删除 top-level `max_tokens` 字段。
  - 删除 top-level `fallbacks` 字段。
- `2.1.257`：同样清空 top-level `model` 并删除 top-level `max_tokens`，但
  `fallbacks` 必须按最终精确模型决定：
  - `model=claude-fable-5` 或 `model=claude-fable-5-1` 时保留
    `fallbacks="default"` 参与 CCH。
  - 其他模型仍删除 top-level `fallbacks`。
- `2.1.260`：继续清空 top-level `model`、删除 top-level `max_tokens`；已观察的
  `claude-fable-5-1` 保留 `fallbacks="default"`，Opus、Sonnet 和 Haiku 删除不存在的
  top-level `fallbacks`。没有 `2.1.260 claude-fable-5` 抓包时，不得外推其 fallback
  或 CCH 裁剪规则。
- `2.1.280` / `2.1.293`：保留相同 seed，删除 top-level `max_tokens`，保留最终请求中的 top-level
  `fallbacks`；对序列化 JSON 中每个 key 字节精确等于 `"model"` 且 value 为字符串的字段
  清空值，包括 advisor 工具和 fallback 对象里的嵌套模型。不得改写字符串正文中的
  `\"model\"`、转义 key（例如 `"\u006dodel"`）或非字符串 model 值。
- `2.1.260` 及更早画像的 CCH 输入裁剪必须只作用 top-level JSON 字段；2.1.280/293 的全层级
  model 清空是独立版本契约，不能反向套用到旧画像。
- 不要先 `serde_json` 反序列化再重新序列化后计算 CCH；字段顺序、转义和空格变化会改变结果。

Beta 顺序契约：

## 原文 424—429 行

- HTTP/1 大小写必须检查实际 TCP 字节。`ordered_anthropic_headers` 给出顺序和拼写，业务
  forwarding/count_tokens 再通过 `http1_header_casing` 显式传给固定版本的 reqwest/hyper
  补丁；Content-Length 只指定名称拼写，长度由最终 body 自动生成。遥测 event_logging/eval
  不启用，默认请求行为不变；HTTP/2 仍使用规范要求的小写名字。
- 依赖补丁与来源见 `cc2api/vendor/README.md`。升级不得仅修改 HeaderMap 或使用全局
  Title-Case 冒充精确混合大小写；克隆、重定向、代理及敏感头删除必须回归。

## 原文 1599—1747 行

## Scenario: Messages 保留调用方流式选择

### 1. Scope / Trigger

- Trigger：修改 `/v1/messages` 的 API mimicry、原生 CC 正文改写或最终响应转发时适用。
- 同一请求的流式选择必须贯穿最终上游正文，不能因软件画像而把非流请求强制变成 SSE。

### 2. Signatures

- 入口：`POST /v1/messages`，JSON 顶层 `stream` 为可选布尔值。
- `detect_client_type` 按原始 UA 的 `claude-cli/`／`claude-code/` 前缀识别 CC，其余为 API；使用 cc2api APIKey 不决定客户端类型。
- 正文改写位于 `Rewriter`；响应由 `GatewayService` 转发实际上游协议，不新增聚合器、设置项或数据库字段。

### 3. Contracts

- API 与 CC 均保留 `stream=false`、`stream=true` 和字段缺省三种状态；缺省不补 true。
- API 画像的系统提示词、tools、默认模型参数与顶层字段排序继续执行，但排序不能额外生成 stream。
- false／缺省交给上游按非流默认处理，true 请求流式；Gateway 转发上游实际返回的 Content-Type 和正文，不自行把 JSON 转为 SSE。
- `Body::from_stream` 只描述 HTTP 字节传输，不能据此判断应用协议为 SSE。
- 最终 CCH 仍基于实际序列化正文计算。本项不增加 stream 类型纠正或非法值处理，沿用上游校验。

### 4. Validation & Error Matrix

| 调用方 stream | 最终上游字段 | 本地协议感知上游的响应 | 下游结果 |
| --- | --- | --- | --- |
| false | false | application/json | 完整 JSON Message |
| true | true | text/event-stream | 保留 SSE，包含 message_stop |
| 缺省 | 缺省 | application/json | 完整 JSON Message |

上述矩阵同时覆盖 API 与 CC。协议感知上游是 loopback 合成服务，不等于已对真实账号完成推理验证。

### 5. Scenarios and Examples

- 正常：普通 SDK 发送 `{"stream":false}`，改写后仍为 false，Gateway 返回上游完整 Message。
- 边界：请求省略 stream，最终正文仍无此字段；Haiku probe 的顶层顺序断言也不得要求额外 stream。
- 错误用法：因为 API 请求需要 CLI 画像就无条件补 `stream=true`，使非流调用方收到 SSE。
- 正确处理：软件画像适配与流式选择独立，直接保留调用方字段，让上游选择对应响应形式。

### 6. Tests Required

- `messages_rewrite_preserves_explicit_stream_preference`：260／280／293 × API／CC × false／true，通过公共改写入口断言最终序列化值。
- `messages_rewrite_preserves_missing_stream_preference`：相同版本与客户端矩阵断言缺省 stream 未被新增。
- `gateway_preserves_stream_preference_through_upstream_and_response`：真实 Gateway + loopback 上游，按上游实际接收参数选择 JSON／SSE；覆盖 API／CC × 三种状态，断言最终参数、Content-Type、完整 JSON 的内容和结束原因或 SSE 结束帧。
- Rust 格式检查与完整 `cargo test --locked` 必须通过；不以仅检查内部 Map 的测试替代出站／返回契约。

## Scenario: Messages 固定顶层字段清理开关

### 1. Scope / Trigger

- Trigger：修改 Messages 顶层清理、全局开关、classifier 旁路或最终 CCH 时适用。
- 固定集合为 `MESSAGE_TOP_FIELD_DROP_KEYS` 的 56 个精确键，与 `tests/fixtures/messages-top-field-drop-keys.json` 逐项一致；来源 VM 版本固定，不在线同步、不生成官方字段白名单。

### 2. Signatures

- 持久化键 `message_top_field_filter_enabled`，默认常量 `DEFAULT_MESSAGE_TOP_FIELD_FILTER_ENABLED="true"`；管理 GET/PUT 沿用 `SettingsMap = Record<string,string>`。
- `Rewriter::filter_message_top_fields(body: &Value, path: &str, enabled: bool) -> Option<Vec<u8>>` 仅在真正删除根键时返回 Some。
- `Rewriter::refresh_message_top_field_filter_cch(&self, body: Vec<u8>, account: &Account) -> Vec<u8>` 复用唯一根级定位、版本化私有刷新与请求账号画像。
- `GatewayService::reload_message_top_field_filter_enabled(&self) -> Result<(), AppError>` 为 async，使用独立 RwLock 缓存；main 启动与 PUT 后调用。

### 3. Contracts

- 精确 `/v1/messages` 的普通 API／CC、classifier attribution 与 identity-only 三条转发分支统一消费可选过滤正文。count_tokens、其它路径、本地 mock／拒绝／缓存命中不扩大。
- 保留原始 body_map/body_bytes 用于准入、sticky、RPM、classifier、会话池和诊断；请求在重试循环前冻结一次开关，换号／401 等重试复用。
- 仅删除精确根键，使用稳定 `shift_remove`；保留其它根键相对顺序、未知扩展、嵌套同名键、metadata.user_id、工具 schema／输入与文本。不展开 extra_headers/extra_body，不提升认证，不做协议转换。
- 关闭、无命中、非对象或不可解析时不生成过滤正文，保留原字节路径；不得无条件再做全量 JSON 往返。
- 普通／归因分支先清理再按既有逻辑封口；实际删除后统一对最终输出刷新已有唯一受管理 CCH。缺失／非法／歧义目标按 F01 失败开放，不新增 billing／identity／CCH。
- 窄刷新不经过旧公开签名重试刷新入口的 CC Strip 门禁，但不能改变该旧入口语义。identity-only 函数本身仍只改身份；新增过滤阶段在外部处理必要的已有 CCH 刷新，不扩展 detector。
- classifier 的这一独立清理例外不启用 expansion、thinking、TTL、缓存断点、通用排序或完整日志；无实际删除时保持原旁路字节行为。
- SQLite／PostgreSQL 默认插入只补缺键，保留显式 false。PUT 仅接受精确字符串 true/false，在任何写入前校验；GET/reload 对缺失和历史非法值统一回退 true，读取失败保留旧缓存。保存后新请求生效。
- UI 默认开启，读写真实 key，保存字符串值；开关 false 可回滚新增清理。stream 三态、身份与 Session 策略继续独立适用。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 开启＋命中根键 | 稳定删除，最终已有 CCH 匹配正文 |
| 关闭或无命中 | 不新增序列化／CCH 刷新 |
| 嵌套同名键／未知扩展 | 保留内容和相对顺序 |
| classifier Strip／归因失败开放 | 独立清理生效，只刷新已有唯一合法目标 |
| 缺键／历史非法设置 | GET 与运行时统一开启 |
| 显式 false／重复迁移 | 保留关闭 |
| 非法 PUT 与其它合法键一起提交 | BadRequest，均不落库 |
| 401 等重试期间切换开关 | 本请求复用原快照，下个请求使用新值 |

### 5. Scenarios and Examples

- 正常：删除根级 `settings`，保留 `metadata.user_id` 和工具 `input_schema.properties.settings`。
- 边界：原始 JSON 无待删键时，identity-only 继续使用原字节；已有 billing 没有 CCH 时不补 CCH。
- 错误：只在普通 rewrite 分支删键，漏掉 classifier；或先封好 CCH 再删键且不刷新。
- 正确：三分支共同入口过滤，有删除才最终刷新已有目标，保留原公开刷新门禁和探针 detector。

### 6. Tests Required

- `gateway_message_top_field_filter_covers_frozen_keys_and_nested_data`、`message_top_field_filter_preserves_order_and_no_change_boundary`：56 键逐项／混合、开关、精确匹配、未知／嵌套与顺序。
- classifier bypass／existing_cch、普通 final_cch_profiles_and_modes、最终组合入口和失败开放测试：280／293、Rewrite／Strip、已有／缺失／非法／歧义 CCH；区分实际 Gateway 与组合入口证据。identity-only 加独立 billing 当前不能通过窄 detector，不声称该组合端到端可达。
- settings 与 DB 测试：默认、幂等迁移、显式 false、非法原子拒绝、GET/reload 一致、读取失败、热刷新和请求快照；核查两种 SQL 方言。
- count_tokens／其它路径隔离、stream 三态、会话身份、工具顺序及 F01 CCH 回归。
- Rust 格式／全量／CCH、前端 TypeScript/Vite 构建和真实 SFC setup 读写断言；后者不冒充浏览器 DOM 点击验证。

## Scenario: Messages beta 多值与查询参数规范化

### 1. Scope / Trigger

- Trigger：修改 Gateway 的重复 anthropic-beta 收集、Messages URL 的 beta query 或 count_tokens 共用入口时适用。
- 修复调用方等价 beta 集合因多行头而丢值，以及 beta=false 与追加的 true 并存；不改变账号能力或版本画像。

### 2. Signatures

- `extract_headers(headers: &HeaderMap) -> HashMap<String, String>` 为普通 Gateway 与 count_tokens 共用入口。
- `merge_anthropic_beta(required: &str, incoming: &str) -> String` 继续按逗号拆分、trim、精确去重并保留首次顺序。
- `upstream_url_with_base(upstream_base: &str, path: &str, query: &str) -> String` 构造通用出站 URL。
- `is_beta_query_key(key: &str) -> bool` 只执行一次解码后的精确键比较。
- `requires_upstream_beta_query(path: &str) -> bool` 只匹配精确 `/v1/messages` 与 `/v1/messages/count_tokens`；后者的专用发送入口仍由 `count_tokens_upstream_url_with_base` 固定唯一 `?beta=true`。

### 3. Contracts

- 仅 anthropic-beta 使用 `HeaderMap::get_all(...).iter()` 按同名值插入顺序合并全部可转字符串的值；头名大小写由 HeaderMap 处理，token 仍大小写敏感且完整匹配。
- 有效空 beta 保留“头存在”的语义；全部无法转字符串时跳过。其它头保留既有覆盖与非法字符串跳过策略，不新增 UA、request-id 或 Authorization 的逗号拼接规则。
- 收集后继续经过账号 1M／Fast 过滤和版本画像合并。1M 仍要求客户端携带且账号允许，并按画像放在 oauth 后；Fast 不主动开启。API、293 safeguard／title／后台窄表不因本修复扩大。
- 目标路径对解码后精确小写键 beta 归一成唯一 `beta=true`，替换首个同名项并删除后续重复；不存在则追加。只对键一次百分号解码，覆盖 false、空、无等号、编码同名与混合重复，不递归解码。
- 其它 query 片段及值的原始编码、大小写、顺序、空片段和重复保留；畸形或双重编码键若不精确匹配 beta，仍按其它原始片段保留。非目标路径不扩大改写，count_tokens 专用 URL 保持既有合同。
- 不建立全局 query 白名单，不以样本未出现为由删除未知扩展，也不把研究夹具的 synthetic_client_id 当作原生 CLI 必须删除的参数。
- 本修复只改头收集与 URL，不改 body、CCH、stream、R2 根键清理开关或 Session／探针／池优先级；没有新 setting、依赖或迁移。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| beta 拆成两行、重叠或有空白 | 有效 token 合并去重，首次顺序保留 |
| 交换两行，账号允许／禁止 1M 或 Fast | token 集合不再因覆盖丢失，能力过滤仍独立生效 |
| 两行 beta 在 API／title／safeguard／后台入口 | 沿用各自画像，不混入未允许的 token |
| 目标 query 缺 beta、false、空或重复冲突 | 最终只含一个 beta=true |
| 一次编码的 beta 键 | 与字面同名项共同归一 |
| 非 beta 原始片段／非目标路径 | 保留其原始形式及既有路径行为 |

### 5. Scenarios and Examples

- 正常：两行分别包含 1M 与普通 beta，合并后再按账号权限过滤；未知 token 相对顺序仍按首次出现，不承诺任意换行后最终字节完全相同。
- 边界：`x=%2f&%62eta=false&beta=true&x=%2F` 变为 `x=%2f&beta=true&x=%2F`，其它编码和重复值保留。
- 错误：只在缺少原始字面 beta=true 时追加，留下 false/true 冲突；或整条 URL 解析再序列化，改变其它原始参数。
- 正确：仅识别同名键并替换 beta 片段，不用 VM 重建全部 query 的行为替代本地兼容合同。

### 6. Tests Required

- `gateway_beta_headers_merge_before_account_filters`：实际 Gateway＋loopback 覆盖 280／293 普通重复头交换、重叠空段、头名大小写、相似 token、1M／Fast 允许和禁止；观察最终 beta 集合及既有已知 token 顺序。
- `gateway_beta_headers_preserve_special_and_api_profiles`、`gateway_beta_count_tokens_merges_before_account_filters`：实际 API、293 safeguard／title／后台和 count_tokens 验证窄画像／计数专用 beta 保留；其它单值头仍按原策略。
- `gateway_beta_query_normalizes_keys_and_preserves_raw_fragments`、`gateway_beta_query_preserves_non_target_paths`：实际上游 URI 覆盖缺省／true／false／空／无等号／重复／百分号同名键、畸形与双重编码、其它 raw 参数重复和空片段、非目标路径及 count_tokens 专用入口；不以中间 Map 断言替代。
- `gateway_beta_headers_preserve_empty_invalid_and_single_value_semantics`：实际区分空 beta 与缺头／非法值，验证其它单值头和入站认证过滤策略。
- R2 清理／Session（含边缘 SP／HTAB）、stream 三态与 CCH 回归、Rust 格式及全量测试通过；仅使用本地合成上游。
