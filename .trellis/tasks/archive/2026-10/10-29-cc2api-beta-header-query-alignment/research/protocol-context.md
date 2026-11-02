# beta 相关协议规范摘录

生成时来源：`.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`；SHA256：`7fb6a23e639aa20a44e53898333ec9d8e9fa40f9cd24a41906784c1d391c6e11`。只节选固定协议规则；完整来源可按需读取。

## 原文 215—305 行

- `2.1.260` 及更早画像的 CCH 输入裁剪必须只作用 top-level JSON 字段；2.1.280/293 的全层级
  model 清空是独立版本契约，不能反向套用到旧画像。
- 不要先 `serde_json` 反序列化再重新序列化后计算 CCH；字段顺序、转义和空格变化会改变结果。

Beta 顺序契约：

- `context-1m-2025-08-07` 不放进通用必需 beta；它由账号 `allow_1m_models` 和客户端传入 beta 共同决定。
- 当允许 1M 并保留 `context-1m-2025-08-07` 时，顺序必须整理为 `oauth-2025-04-20` 后、`interleaved-thinking-2025-05-14` 前。
- `2.1.257 claude-fable-5` 无 1M 主请求顺序：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-07-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

`2.1.260` 主请求必须按精确模型使用下列 beta，不能把 Fable 5.1 的 token 合并到通用
画像：

Opus 5 `[1m]`：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,fallback-credit-2026-06-01,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Sonnet 5：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Fable 5.1：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,per-turn-control-2026-07-01,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-07-01,fallback-credit-2026-06-01,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Haiku main（有 diagnostics）：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,claude-code-20250219,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Haiku main 无 diagnostics 时只移除 `claude-code-20250219`；probe、title 和 non-stream
aux 继续使用 `2.1.257` 已确认的独立窄画像。

`2.1.280` 必须按精确模型使用 `version_profile.rs` 中的 280 常量；共同新增的顺序约束为：

- Opus 5.5 与 Fable 5.1 包含 `per-turn-control-2026-07-01`、
  `mid-conversation-tool-changes-2026-07-01`、`mid-conversation-system-clear-at-2026-08-21`、
  `thinking-binding-controls-2026-08-01`，不在基础画像中主动加入 fallback token。
- Sonnet 5 不含 per-turn/tool-changes，包含 system-clear、thinking-binding，并在末尾追加
  `message-threads-2026-08-12`。
- Opus 4.8 普通请求包含 tool-changes、system-clear、effort、thinking-binding 和末尾
  message-threads，不含 per-turn；带 `dangerous_tool_use` safeguard 的 Auto/Plan 请求改用专属
  精确画像，移除 message-threads，并在 effort 后加入 `dangerous-tool-use-2026-09-03`、在
  display 后加入 `afk-mode-2026-01-31`。
- Opus 5.5 带 `dangerous_tool_use` safeguard 的 Auto/Plan 请求同样使用专属精确画像，在
  effort 后加入 `dangerous-tool-use-2026-09-03`、在 display 后加入
  `afk-mode-2026-01-31`；普通请求继续使用基础 Opus 5.5 画像。
- Sonnet 4.5 不含 mid-conversation-system、effort、per-turn 与 tool-changes，保留
  thinking-binding/display。API 生成模式在末尾追加 `message-threads-2026-08-12`；原生
  Claude Code 模式由客户端决定是否携带该 token，不从 `thread` 正文或模式推测开关。
  `MainRequestProfile.client_optional_beta_tokens` 声明此差异：先从 required 集合移除，
  再合并经过账号能力过滤的客户端 beta；不影响 1M/Fast、safeguard 或 count_tokens。
- Haiku main 在 2.1.260 基础上于 display 前新增 `thinking-binding-controls-2026-08-01`；
  无 diagnostics 时仍只移除 `claude-code-20250219`。
- 1M token 仍只在客户端传入且账号白名单允许时插入 oauth 后；仅当 endpoint 精确为
  `/v1/messages` 且最终请求包含非 null `fallbacks` 时，fallback beta 才由动态规则插入，
  不能写进基础模型常量。`/v1/messages/count_tokens` 即使带 `fallbacks` 也只能使用
  count_tokens 专用 beta，不得继承消息生成的 fallback token。

- 当目标版本已经声明非空的精确 `main_models` 时，Haiku main 必须先通过
  `RequestProfile::main_model(model_id)` 精确命中，才能使用该版本的 Haiku main beta；
  未观察的 Haiku 模型回退版本级 `message_beta_tokens`，不能只因 ID 包含 `haiku` 就套用
  新画像。probe、title 和 non-stream aux 属于已有独立证据的请求类型，仍可沿用现有
  Haiku 分类；没有精确 `main_models` 的旧画像继续保持已验证的历史族分类行为。

- Fable `[1m]` 的主请求画像必须按目标版本抓包判断，不能只从 CLI model 后缀推断：
  - `2.1.172` 抓包中，Fable `[1m]` 主请求包含 `context-1m-2025-08-07`，顺序如下。
  - `2.1.173` 抓包中，Fable `[1m]` 主请求不包含 `context-1m-2025-08-07`，只在 telemetry 启动配置里体现 `cli_flag=claude-fable-5[1m]`。
  - `2.1.257` 的 `claude-fable-5-1[1m]` 入口解析后的 message 请求使用精确模型
    `claude-fable-5-1`，不自动携带 `context-1m-2025-08-07`。
  - 当前没有 `2.1.260 claude-fable-5-1[1m]` message 样本；继续保持“不主动注入 1M”
    的兼容行为，但不得宣称该入口已在 `2.1.260` 重新验证。
  - 账号 `allow_1m_models` 只控制客户端已有 `context-1m-2025-08-07` 是否透传，不应自动给 Fable 主请求注入 1M beta。

`2.1.172` Fable `[1m]` 主请求顺序：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```


## 原文 378—420 行

- main 有 `diagnostics` 时使用完整 Haiku main beta；无 `diagnostics` 时省略
  `claude-code-20250219`；probe、title、non-stream aux 各使用画像中的独立窄 beta。

标题可选 beta 契约：

- 2.1.257/2.1.260 的标题基础窄画像之外，只保留客户端已携带的
  `server-side-fallback-2026-07-01`、`fallback-credit-2026-06-01`；按此顺序去重，
  插入 `cache-diagnosis-2026-04-07` 前。没有携带时不主动开启。
- token 按逗号拆分、去空白后精确匹配；旧日期、相似后缀和父模型的其他 beta 不合入。
- 两种客户端入口共用最终规范化。旧画像的可选列表为空；probe 不保留这些 token。

后台 UA/beta 契约：

- 2.1.257/2.1.260 使用 `EndpointHeaderProfile::ClaudeCode21257`；2.1.280 使用
  `ClaudeCode21280`，继承下表并追加后面的 280 规则。下表的 12 类
  路径来自 260 原始 flow；257 JSONL 可核对其中 10 类，stream/archive 不在该索引中。
- `{id}` 必须是非空单一路径段，后缀精确匹配；相似路径、未知子路径、额外尾斜杠
  不自动套用。旧画像使用 `Legacy`，保留既有行为。
- 两种客户端入口都在通用 header 处理后应用下表；“无”表示删除传入 beta。

| 路径 | User-Agent | anthropic-beta |
| --- | --- | --- |
| `/v1/code/sessions`、`/v1/code/sessions/{id}/bridge` | `claude-code/<version>` | 无 |
| `/v1/code/sessions/{id}/worker`，以及其 `/events`、`/events/stream`、`/internal-events`、`/heartbeat` | `claude-code/<version>` | 无 |
| `/v1/code/sessions/{id}/client/presence` | `axios/1.15.2` | 无 |
| `/v1/sessions/{id}`、`/v1/sessions/{id}/archive` | `claude-code/<version>` | `ccr-byoc-2025-07-29` |
| `/api/claude_code/notification/preferences` | `claude-cli/<version> (external, cli)` | `oauth-2025-04-20` |
| `/v1/ultrareview/quota` | `claude-cli/<version> (external, cli)` | 无 |

以上契约只覆盖 UA/beta，不代表 worker JWT、完整请求头顺序、响应或长连接代理已实现。

2.1.280 非遥测补充契约（本地与正式抓包对照）：

| 路径 | User-Agent | anthropic-beta / 专用请求头 |
| --- | --- | --- |
| `/api/frame/contract/latest` | `claude-cli/2.1.280 (external, cli)` | 精确 oauth；保留 `X-Frame-CP`、`X-Frame-Surface`、`X-Frame-Platform`、`X-Frame-Client-Version`、`X-Frame-Session-Id`，版本来自所选画像 |
| `/v1/mcp/{id}` | `claude-code/2.1.280 (cli)` | 无 beta；保留 `X-Mcp-Client-Session-Id`、`mcp-method` |
| `/api/organizations/{id}/model_selector/cc` | `claude-cli/2.1.280 (external, cli)` | 无 beta |
| `/api/oauth/organizations/{id}/marketplaces`、`plugins/list-plugins`、`skills/list-skills`、`skills/{id}/download` | 同上 | 无 beta |

- 新端点规则仍按非空路径段和精确后缀匹配，近似路径不放宽；旧版本 UA/beta 不套 280 规则。
- 原生 `/v1/messages` 透传 `x-claude-code-request-class` 和
  `x-claude-code-prev-tool-durations`；其它端点丢弃这两项，不在 API 请求中伪造工具耗时。

## 原文 956—1031 行

- Trigger: 新增或修改 `fast-mode-2026-02-01`、账号级 beta 放行开关、`/v1/messages` / `count_tokens` beta 合并，或 bench 创建 cc2api 账号的同步契约。
- 本场景属于跨层契约：账号模型、SQLite/PostgreSQL schema、Store、管理 API、Accounts UI、协议重写和 bench 同步必须保持一致。
- Fast Mode 的产品语义是“允许透传客户端已有 token”，不是由 cc2api 主动开启。

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
- 当 `allow_fast_mode=false` 时，按逗号拆分并精确删除完整 token `fast-mode-2026-02-01`；不得使用子串替换，其他 beta token 保持原始相对顺序。
- 当 `allow_fast_mode=true` 时，只保留客户端显式携带的 Fast Mode token；版本画像和网关不得主动注入该 token。
- `/v1/messages` 与 `/v1/messages/count_tokens` 必须复用同一账号 beta 过滤策略；`count_tokens` 过滤后仍必须合并 `token-counting-2024-11-01`。
- `context-1m-2025-08-07` 继续由 `allow_1m_models` 控制，Fast Mode 改动不得扩大或收窄现有 1M 白名单。
- 要求精确 beta 画像、不会合并客户端 beta 的特殊请求保持现有 required beta，不因账号开关主动增删 Fast Mode。
- 过滤发生在最终上游 header 生成之前；不得修改请求体、CCH、`cc_version` 或默认版本画像。
- bench 首次创建 cc2api 账号时，payload 必须显式发送 `"allow_fast_mode": false`，不能只依赖 cc2api 默认值。
- bench 匹配既有账号或已绑定账号时，只校验身份、绑定并同步 OAuth 凭据；不得调用账号配置更新接口覆盖 `allow_fast_mode`。该配置的唯一权威来源是 cc2api，bench 数据库不复制该字段。

### 4. Validation & Error Matrix

| 条件 | 期望 |
|------|------|
| 客户端携带 Fast Mode，账号字段缺失或为 `false` | 最终 `anthropic-beta` 不包含完整 Fast Mode token |
| 客户端携带 Fast Mode，账号字段为 `true` | 最终 header 保留该 token，且只出现一次 |
| 客户端携带 `fast-mode-2026-02-01-extra` | 不得误删，精确匹配只删除完整 token |
| 客户端未携带 Fast Mode，账号字段为 `true` | 不主动注入 Fast Mode |
| Fast Mode 与 1M token 同时出现 | 两个策略分别判断，保留 token 的相对顺序和 1M 抓包顺序整理规则 |
| `count_tokens` 默认禁止 Fast Mode | Fast Mode 被删除，`token-counting-2024-11-01` 仍存在 |
| 旧数据库新增列 | 历史账号得到 `0`，升级后默认禁止 |
| bench 创建新 cc2api 账号 | create payload 明确包含 `allow_fast_mode=false` |
| bench 匹配既有 cc2api 账号 | 不创建账号、不更新账号配置，管理员原值保持不变 |

### 5. Good/Base/Bad Cases

**Good**：管理员在 Accounts 页面为单个账号显式开启；只有客户端同时携带 Fast Mode token 时，上游请求才包含该 token。

**Base**：新账号、旧库迁移账号和 bench 首次同步账号全部默认禁止，普通请求的其他 beta、CCH 和 `cc_version` 保持不变。

**Bad**：把 Fast Mode 加进版本画像 required beta，导致管理员只是允许透传却变成所有请求主动开启。

## 原文 1459—1563 行

### 1. Scope / Trigger

- 修改 293 软件身份、精确模型、标题、beta、线程/CCH、后台端点、默认配置或管理页时适用；旧画像必须保持独立，不能因切换默认画像而改变 280 wire。
- 证据来自正式抓包任务的 25 轮、四模型六权限模式，112 条 billing 的 CCH/后缀全部独立复查命中。矩阵固定 xhigh；其它 effort 以及同时带 safeguard 与 fallback 的组合不计入真实采集覆盖。合成测试不能替代抓包。
- 原始正文只留受限远端；仓库 fixture 使用合成文本和身份，保留协议形状、顺序及独立期望值。遥测扩展与自动部署不属于本次升级。

### 2. Signatures

```text
GET /admin/settings -> JSON 字符串映射
PUT /admin/settings <- JSON 字符串映射
SettingsStore::upsert_many_with_profile(
    &self,
    items: &HashMap<String, String>,
    profile: Option<&'static ClaudeCodeProfile>,
) -> Result<(), AppError>  // async
GatewayService::reload_access_profile_config(&self) -> Result<(), AppError>  // async
is_structured_haiku_title_request_for_profile(
    body: &serde_json::Value,
    request_profile: &RequestProfile,
) -> bool
upgrade_default_profile_setting(pool: &AnyPool, driver: &str) -> Result<(), sqlx::Error>  // async
use280293AccessPreset(): void
```

请求相关结构分别由 `ClaudeCodeProfile.request/billing/endpoints` 声明；293 使用 `HaikuTitleProfile::ClaudeCode21293`、`MessageBodyOrderProfile::ClaudeCode21293`、`EndpointHeaderProfile::ClaudeCode21293` 与 `CchProfile::ClaudeCodeAllModelValues`，不新增自由输入版本或环境变量。

### 3. Contracts

**身份与模型**

| 字段 | 293 值 |
| --- | --- |
| version / version_base / 默认 profile key | `2.1.293` |
| build_time | `2026-10-07T06:36:42Z` |
| Stainless SDK / Node / timeout | `0.128.0` / `v26.3.0` / `600` |
| Hello UA | `Bun/1.4.3` |
| 出厂允许范围 / 禁止版本 | `2.1.89-2.1.293` / 空字符串 |

257/260/280 的 SDK 固定为 `0.112.1`，不能引用已经切换为 293 的全局默认 SDK。260/280 的 registry、精确 UA 映射、页面选项与旧模型处理继续保留。

| 精确主模型 ID | 默认 max_tokens / 293 API 上限 | thinking | 默认 effort | bootstrap cwk |
| --- | --- | --- | --- | --- |
| `claude-opus-5-5` | 128000 | adaptive，display=updates | xhigh | saffron |
| `claude-sonnet-5-5` | 128000 | adaptive，display=updates | xhigh | cardamom |
| `claude-haiku-5-5` | 128000 | adaptive，display=updates | xhigh | lovage |
| `claude-fable-5-1` | 64000 | adaptive，display=updates | xhigh | sorrel |

只对这些精确 ID 使用新表；其它模型和旧画像沿用已有行为，旧画像 API 的 64000 上限保持原契约。已有显式 effort 选择规则保留，不能宣称所有档位都已抓包。Fable 的 CLI `[1m]` 后缀不证明 wire 存在 context-1m 或 fallback，本矩阵没有观察到这两项；不自动补入。bootstrap 的 `client_data.cedar_basin=2027-08-31`，未涉及的上游字段保留。

**Beta 与标题**

Opus/Sonnet/Fable 普通主请求的基线按如下顺序维护，不包含自动启用的 context-1m：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,per-turn-control-2026-07-01,mid-conversation-tool-changes-2026-07-01,inline-tools-2026-09-15,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,mid-conversation-system-clear-at-2026-08-21,effort-2025-11-24,thinking-binding-controls-2026-08-01,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07,message-threads-2026-08-12
```

- Haiku 5.5 普通主请求从 oauth 开始，`claude-code-20250219` 位于 mid-conversation-system 后、per-turn-control 前，其余顺序与基线一致。原生客户端的 claude-code 与 extended-cache-ttl 两个 token 按入站是否携带决定，不依据权限模式、diagnostics 或 thread 猜测；293 API 缺少该客户端选择信息时使用完整基线。
- 四模型 Auto/Plan 已观察 safeguards：dangerous-tool-use 插在 effort 后，afk-mode 插在 thinking-display-updates 后、extended-cache-ttl 前。使用精确 safeguard 表，不能合并任意未知 beta；已验证的客户端可选 token 按原位置保留。
- Opus 原生 context-1m 需要客户端已携带 token 且账号允许 1M；位置在 oauth 后。不得从账户权限单独推断启用。
- 已观察 Opus 普通 `fallbacks="default"`：server-side-fallback、fallback-credit 依次位于 effort 后、thinking-binding-controls 前；保留 fallback 参与 CCH。不得据此自动生成其它模型的默认 fallback 或声称 safeguard+fallback 组合已采集。
- 293 标题必须为精确 `claude-haiku-5-5`、stream=true、tools 为空或缺省、max_tokens=128000、thinking 字段缺省，且 `output_config.format` 的 schema 仅要求 title。不得用旧 32000 token 标题判定把它归到主请求。
- 标题的精确 beta 顺序如下；旧 Haiku 4.5 自动单 token 探测仍使用原有窄表，不属于新主模型升级。

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,per-turn-control-2026-07-01,mid-conversation-tool-changes-2026-07-01,inline-tools-2026-09-15,advisor-tool-2026-03-01,mid-conversation-system-clear-at-2026-08-21,effort-2025-11-24,structured-outputs-2025-12-15,cache-diagnosis-2026-04-07
```

**字节与会话**

293 顶层已知字段顺序为 `model,messages,system,tools,metadata,max_tokens,thinking,context_management,fallbacks,safeguards,output_config,thread,diagnostics,stream`；缺省字段不因排序而插入，未知字段保持相对顺序，SSE 与 safeguard_results 保持字节透传。

CCH 使用 `0x4D659218E32A3268`：在最终序列化字节上将唯一受管理根级 system billing 的 CCH 替为占位值、删除顶层 max_tokens、清空全层级精确字符串 model 值，保留 fallback，再取 xxhash64 低 20 bits。禁止 JSON 往返重排。初始后缀仍以 salt `59cf53e54c78`、首条 user 的最后一个 text block、UTF-16 code units `[4,7,20]` 与版本计算 SHA256 前三位；缺失索引按既有 `0` 规则，孤立代理项按既有替换字符语义处理。续轮使用当前入站 billing 后缀；审计通过 previous_message_id 对应前一 SSE message_start.id 逐链检查，同 run/model 不构成唯一会话键，也不新增全局后缀缓存。

**后台端点**

以下为本轮已观察的精确分支；其它路径不得按 293 版本号套用旧版后台端点分类。

| 端点 | 方法 | UA | beta | Content-Type | anthropic-version |
| --- | --- | --- | --- | --- | --- |
| `/api/hello` | HEAD | Bun/1.4.3 | 无 | 无 | 无 |
| `/api/eval/*` | POST | claude-code/2.1.293 | oauth-2025-04-20 | application/json | 无 |
| `/api/claude_code_grove` | GET | claude-cli/2.1.293 (external, cli) | oauth-2025-04-20 | 无 | 无 |
| `/api/claude_code_penguin_mode` | GET | claude-code/2.1.293 | oauth-2025-04-20 | 无 | 无 |
| `/api/claude_cli/bootstrap` | GET | claude-code/2.1.293 | oauth-2025-04-20 | application/json | 无 |
| `/v1/mcp_servers` | GET | claude-code/2.1.293 | mcp-servers-2025-12-04 | application/json | 2023-06-01 |

Hello/eval 的 Accept 为 `*/*`、Accept-Encoding 为 `gzip, deflate, br, zstd`；其余四项为 `application/json, text/plain, */*` 与 `gzip, compress, deflate, br`。MCP capability 沿用280常量，协议版本为 `2025-11-25`。280 的 eval Bun 与 penguin/MCP Axios 身份保持原样。

**配置与管理页面**

预设 `use280293AccessPreset` 只填入以下四个表单字段，保存后才生效；不得顺带改 UA、遥测开关或删除260选项：

```json
{
  "claude_code_profile_selection_mode": "client_version",
  "claude_code_version_profile": "2.1.293",
  "allowed_claude_code_versions": "2.1.89-2.1.293",
  "blocked_claude_code_versions": "2.1.89-2.1.279,2.1.281-2.1.292"
}
```

禁止规则优先于允许范围，准入通过后才选择画像。默认回退无法放行被禁版本。客户端模式允许范围独立保存；账号模式使用目标画像范围并只读回显。主动保存画像仍在同一事务中更新全部账号四项软件字段；启动迁移仅处理客户端模式的精确旧出厂组合，账号模式和自定义策略保留，详见 [Settings & Database](../backend/settings-database.md)。账号页基础版本来自持久环境，模式/默认回退来自实际配置，显示「准入通过后」，不得当成最近请求画像。
