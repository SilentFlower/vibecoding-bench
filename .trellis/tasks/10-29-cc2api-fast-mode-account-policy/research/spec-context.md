# 实施阶段相关规范原文摘录

从当前权威规范复制相关完整原文，避免超长文件注入截断。每段标明原文件位置和 SHA-256；源规范再次变化时须回读，不将摘录当作独立权威。

## Gateway 热路径

来源：`.trellis/spec/cc2api/backend/service-architecture.md:27`，范围 27–36。原文件 SHA-256：`4a205ec672fbe1305d5a8a84c70912b1c24cee7f9cd7fc6469aaf2bc7b1cd218`。

## Gateway 热路径规则

`GatewayService::handle_request` / `handle_request_inner` 是最高风险路径。修改前必须明确：

- 请求是否应在账号选择前拦截，例如 assistant prefill、warmup、Auto Mode classifier、非流探针缓存。
- 请求是否会消耗账号并发/RPM；粘性会话下不能因为 RPM 超限随意切号破坏缓存。
- 请求体是否被读取、解压、改写或缓存；读取后转发必须使用最终 body。
- Claude Code 请求改写必须在 CCH 和 `cc_version` 重新计算前完成。
- 上游非成功响应如果要重试，必须保留原有错误体兼容性和敏感信息边界。
- SSE 流式响应只能插入明确允许的 keepalive/comment，不要重排上游 chunk。

## 请求编码合同

来源：`.trellis/spec/cc2api/backend/service-architecture.md:53`，范围 53–65。原文件 SHA-256：`4a205ec672fbe1305d5a8a84c70912b1c24cee7f9cd7fc6469aaf2bc7b1cd218`。

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

## 状态分类旁路合同

来源：`.trellis/spec/cc2api/backend/service-architecture.md:939`，范围 939–964。原文件 SHA-256：`4a205ec672fbe1305d5a8a84c70912b1c24cee7f9cd7fc6469aaf2bc7b1cd218`。

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

## 根级 CCH 与画像约束

来源：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md:181`，范围 181–210。原文件 SHA-256：`69efbc786861bf8e7073ebc50121c69c27e81794fbed962826b72fc73ace1021`。

| 默认允许范围 | `2.1.89-2.1.220` |

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

## Fast 合同及字段定义

来源：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md:954`，范围 954–1014。原文件 SHA-256：`69efbc786861bf8e7073ebc50121c69c27e81794fbed962826b72fc73ace1021`。

### 1. Scope / Trigger

- Trigger: 新增或修改 `fast-mode-2026-02-01`、根级 `speed: "fast"`、账号级 Fast 放行开关、`/v1/messages` / `count_tokens` 正文与 beta 协调，或 bench 创建 cc2api 账号的同步契约。
- 本场景属于跨层契约：账号模型、SQLite/PostgreSQL schema、Store、管理 API、Accounts UI、协议重写和 bench 同步必须保持一致。
- Fast Mode 的产品语义是允许客户端显式申请；禁止时回落普通模式，允许时不替普通请求主动开启。公开 API 的新机制可仅依赖 `speed: "fast"`，不能只靠删除旧 beta 表达禁止。

### 2. Signatures

账号与数据库字段：

```text
Account.allow_fast_mode: bool
accounts.allow_fast_mode INTEGER NOT NULL DEFAULT 0
```

管理 API 字段：

```json
{
  "allow_fast_mode": false
}
```

协议 token 与入口：

```text
fast-mode-2026-02-01
POST /v1/messages
POST /v1/messages/count_tokens
```

关键代码入口：

```text
src/model/account.rs
src/store/db.rs
src/store/account_store.rs
src/handler/router.rs
src/service/rewriter.rs
src/service/gateway.rs
web/src/api.ts
web/src/components/Accounts.vue
orchestrator/main.py::sync_account_to_cc2api
```

### 3. Contracts

- `allow_fast_mode` 默认必须为 `false`：Rust serde 缺省、管理 API 创建缺省、SQLite/PostgreSQL 建表和旧库迁移、前端新建表单都必须一致。
- 当 `allow_fast_mode=false` 时，按逗号拆分并精确删除完整 token `fast-mode-2026-02-01`；同时稳定删除 JSON 根级字符串精确等于 `"fast"` 的 `speed`，按普通模式发送，不新增 Fast 请求拒绝或重试。不得使用子串替换，其他 beta token 保持原始相对顺序。
- 正文过滤使用共享 `Rewriter::filter_account_fast_mode_body(body: &Value, account: &Account) -> Option<Value>`；仅实际删除时复制并返回新对象，`standard`、大小写／空白异常值、其它类型、嵌套同名字段及其它根键的值与相对顺序不变。无删除时不因该策略重新序列化。
- 当 `allow_fast_mode=true` 时，不删除客户端的正文 Fast 申请，Fast beta 沿用入口已有合并规则；版本画像和网关不得主动注入 Fast token 或 `speed: "fast"`。账号放行不扩大 API、title、精确 safeguard 的 beta 合并边界，也不按正文自动补 beta。
- 精确 `/v1/messages` 的 API／原生 CC、流式／非流式、普通／identity-only／classifier attribution 转发在账号确定后统一执行正文策略；其它路径与本地 mock／缓存命中不增加转发。
- `/v1/messages/count_tokens` 复用同一正文与账号 beta 过滤策略；`count_tokens` 过滤后仍必须合并 `token-counting-2024-11-01`，不改变专用入口与方法检查。
- 每次换号都从公共原始逻辑请求派生本次账号正文，不能让前次禁止删除污染后续允许账号，也不能继承前次放行。401 认证恢复复用当前账号正文，签名修复保持已应用策略，不恢复 Fast 字段。
- `context-1m-2025-08-07` 继续由 `allow_1m_models` 控制，Fast Mode 改动不得扩大或收窄现有 1M 白名单。
- 要求精确 beta 画像、不会合并客户端 beta 的特殊请求保持现有 required beta，不因账号开关主动增删 Fast Mode。
- 过滤发生在最终上游 header 生成之前，header 与观测使用本次账号最终正文。实际删减后通过 `Rewriter::refresh_message_body_policy_cch` 刷新已有合法唯一根级 billing CCH，包含 Strip／身份旁路；复用既有定位和版本算法，不新增 billing／CCH、版本或画像。仅该字段删除与必要 CCH 刷新可突破旁路的原始字节保留合同。
- 请求继续按原 Content-Encoding 链在实际发送前重编码，Content-Length 依据最终 wire bytes；冻结编码链覆盖认证、签名与换号重试，不复用首包压缩体。
- bench 首次创建 cc2api 账号时，payload 必须显式发送 `"allow_fast_mode": false`，不能只依赖 cc2api 默认值。
- bench 匹配既有账号或已绑定账号时，只校验身份、绑定并同步 OAuth 凭据；不得调用账号配置更新接口覆盖 `allow_fast_mode`。该配置的唯一权威来源是 cc2api，bench 数据库不复制该字段。

## 固定根字段策略与共享 CCH 刷新

来源：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md:1660`，范围 1660–1678。原文件 SHA-256：`69efbc786861bf8e7073ebc50121c69c27e81794fbed962826b72fc73ace1021`。

### 2. Signatures

- 持久化键 `message_top_field_filter_enabled`，默认常量 `DEFAULT_MESSAGE_TOP_FIELD_FILTER_ENABLED="true"`；管理 GET/PUT 沿用 `SettingsMap = Record<string,string>`。
- `Rewriter::filter_message_top_fields(body: &Value, path: &str, enabled: bool) -> Option<Vec<u8>>` 仅在真正删除根键时返回 Some。
- `Rewriter::refresh_message_body_policy_cch(&self, body: Vec<u8>, account: &Account) -> Vec<u8>` 复用唯一根级定位、版本化私有刷新与请求账号画像，供根字段清理及 Fast 账号策略的实际删除共用。
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

## 多值 beta 合同

来源：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md:1722`，范围 1722–1731。原文件 SHA-256：`69efbc786861bf8e7073ebc50121c69c27e81794fbed962826b72fc73ace1021`。

### 3. Contracts

- 仅 anthropic-beta 使用 `HeaderMap::get_all(...).iter()` 按同名值插入顺序合并全部可转字符串的值；头名大小写由 HeaderMap 处理，token 仍大小写敏感且完整匹配。
- 有效空 beta 保留“头存在”的语义；全部无法转字符串时跳过。其它头保留既有覆盖与非法字符串跳过策略，不新增 UA、request-id 或 Authorization 的逗号拼接规则。
- 收集后继续经过账号 1M／Fast 过滤和版本画像合并。1M 仍要求客户端携带且账号允许，并按画像放在 oauth 后；Fast 不主动开启。API、293 safeguard／title／后台窄表不因本修复扩大。
- 目标路径对解码后精确小写键 beta 归一成唯一 `beta=true`，替换首个同名项并删除后续重复；不存在则追加。只对键一次百分号解码，覆盖 false、空、无等号、编码同名与混合重复，不递归解码。
- 其它 query 片段及值的原始编码、大小写、顺序、空片段和重复保留；畸形或双重编码键若不精确匹配 beta，仍按其它原始片段保留。非目标路径不扩大改写，count_tokens 专用 URL 保持既有合同。
- 不建立全局 query 白名单，不以样本未出现为由删除未知扩展，也不把研究夹具的 synthetic_client_id 当作原生 CLI 必须删除的参数。
- 本修复只改头收集与 URL，不改 body、CCH、stream、R2 根键清理开关或 Session／探针／池优先级；没有新 setting、依赖或迁移。
