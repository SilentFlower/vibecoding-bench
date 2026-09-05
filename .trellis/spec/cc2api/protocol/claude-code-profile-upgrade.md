# Claude Code Profile Upgrade

> 记录 `cc2api` 升级 Claude Code 版本画像时必须执行的协议契约。目标是让未来升级默认画像时，不再只改版本号而漏掉 CCH、`cc_version`、模型子画像、beta 顺序、bootstrap、超时诊断和账号迁移。

---

## Scenario: Claude Code 版本画像升级

### 1. Scope / Trigger

- Trigger: 升级 `cc2api/` 的 Claude Code 默认版本、User-Agent、请求头、CCH、`cc_version`、bootstrap response、telemetry metadata 或账号默认画像。
- 必须使用真实抓包对比，不允许只根据代码常量推断协议。
- 本场景属于跨层契约：请求重写、header profile、body profile、telemetry、DB migration、Web settings 和远程部署都可能一起受影响。

### 2. Signatures

关键代码入口：

```text
src/service/version_profile.rs
src/service/rewriter.rs
src/service/telemetry.rs
src/service/gateway.rs
src/service/session_hello_probe.rs
src/handler/router.rs
src/store/db.rs
src/store/settings_store.rs
web/src/components/Settings.vue
```

关键 wire 字段：

```text
User-Agent: claude-cli/<version> (external, cli)
User-Agent: claude-code/<version>
X-Stainless-Package-Version
X-Stainless-Runtime
X-Stainless-Runtime-Version
X-Stainless-Timeout
anthropic-version
anthropic-beta
x-app
x-anthropic-billing-header: cc_version=<version>.<suffix>; cc_entrypoint=cli; cch=<5hex>;
```

关键 DB 字段：

```sql
accounts.canonical_env.version
accounts.canonical_env.version_base
accounts.canonical_env.build_time
accounts.canonical_env.node_version
settings.claude_code_version_profile
settings.allowed_claude_code_versions
settings.allow_system_role_models
settings.bootstrap_additional_model_options
```

`/api/hello` response signature：

```http
GET /api/hello  -> 200 application/json, body={"message": "hello"}, Content-Length=20
HEAD /api/hello -> 200 application/json, empty body, Content-Length=20
```

抓包目录约定：

```text
data/flows/<account>/<topic_id>/<run_id>/
├── capture_index.json
├── http_capture.jsonl
├── stats.jsonl
└── *.flow
```

### 3. Contracts

版本画像必须集中维护：

- `DEFAULT_CLAUDE_CODE_VERSION`
- `DEFAULT_CLAUDE_CODE_VERSION_BASE`
- `DEFAULT_CLAUDE_CODE_BUILD_TIME`
- `DEFAULT_CLAUDE_CODE_VERSION_PROFILE`
- `STAINLESS_RUNTIME_VERSION`
- `claude_cli_user_agent(version)`
- `claude_code_user_agent(version)`
- `DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS_SETTING`
- `RequestProfile::fable_model(model_id)`
- `RequestProfile::haiku_title_optional_beta_tokens`
- `EndpointProfile::header_profile` / `EndpointHeaderProfile`
- `CchProfile`
- `FableFallbackProfile`

`cc_version` 后缀契约：

- 算法：`sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`。
- 字符索引必须按 JavaScript UTF-16 code unit 语义。
- `messages[0].content` 是数组时，Claude Code 主请求可能先放环境上下文 text block，再放真实用户 prompt text block；后缀文本源应取首条 user message 的最后一个 text block，而不是第一个 text block。
- Haiku/title 这类只有一个 text block 的请求仍取唯一 text block。

`2.1.257` identity 契约：

| 字段 | 值 |
|------|----|
| `version` / `version_base` | `2.1.257` |
| `build_time` | `2026-09-01T05:28:54Z` |
| `User-Agent` | `claude-code/2.1.257` |
| `X-Stainless-Package-Version` | `0.112.1` |
| `X-Stainless-Runtime` | `node` |
| `X-Stainless-Runtime-Version` | `v26.3.0` |
| GrowthBook / session hello UA | `Bun/1.4.1` |
| 默认允许范围 | `2.1.89-2.1.257` |

`2.1.260` identity 契约：

| 字段 | 值 |
|------|----|
| `version` / `version_base` | `2.1.260` |
| `build_time` | `2026-09-03T19:41:35Z` |
| CLI `User-Agent` | `claude-cli/2.1.260 (external, cli)` |
| telemetry `User-Agent` | `claude-code/2.1.260` |
| `X-Stainless-Package-Version` | `0.112.1` |
| `X-Stainless-Runtime` | `node` |
| `X-Stainless-Runtime-Version` | `v26.3.0` |
| GrowthBook / session hello UA | `Bun/1.4.1` |
| `X-Stainless-Timeout` | `600` |
| 默认允许范围 | `2.1.89-2.1.260` |

`2.1.260` 的 endpoint 集合、header 顺序和主请求顶层字段顺序与 `2.1.257` 保持一致；
不得因 patch 版本变化重排已确认的 wire 字段。

`2.1.220` 必须作为独立回滚画像保留，不能复用 2.1.257 的 Stainless、Bun、CCH 或
Fable 5.1 子画像。

`2.1.220` identity 契约：

| 字段 | 值 |
|------|----|
| `version` / `version_base` | `2.1.220` |
| `build_time` | `2026-07-24T22:17:45Z` |
| `User-Agent` | `claude-code/2.1.220` |
| `X-Stainless-Package-Version` | `0.94.0` |
| `X-Stainless-Runtime` | `node` |
| `X-Stainless-Runtime-Version` | `v26.3.0` |
| GrowthBook / hello UA | `Bun/1.4.0` |
| 默认允许范围 | `2.1.89-2.1.220` |

CCH 契约：

- seed 不是默认可变项；升级时先用旧 seed 复算，不命中再尝试找 seed。
- `2.1.156`、`2.1.169`、`2.1.172`、`2.1.173`、`2.1.185`、`2.1.187`、
  `2.1.195`、`2.1.197`、`2.1.220`、`2.1.257`、`2.1.260` 使用 seed
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
- CCH 输入裁剪必须只作用 top-level JSON 字段，不能误删 tool schema、message content 或嵌套对象里的同名字段。
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

Fable body 契约：

- `claude-fable-5` 与 `claude-fable-5-1` 是两个精确模型画像；wire 改写不能用宽泛
  `claude-fable-*` 前缀把二者合并。
- `max_tokens=64000` 默认只在缺失时补齐，不覆盖用户已有值。
- `fallbacks` 必须来自选中的版本画像，只在缺失时补齐，不重复追加，不覆盖用户已有字段。
  - `2.1.257` 的 `claude-fable-5-1` 使用字符串 `"default"`。
  - `2.1.257` 的 `claude-fable-5` 同样使用字符串 `"default"`，不能回退为数组。
  - `2.1.260` 的 `claude-fable-5-1` 使用字符串 `"default"`。
  - `2.1.220` 使用 `[{"model":"claude-opus-5"}]`。
  - `2.1.197` 及旧回滚画像保留 `[{"model":"claude-opus-4-8"}]`。
- `2.1.257 claude-fable-5` 缺少 thinking 时补 `{"type":"adaptive"}`，不补 display；
  `2.1.257 claude-fable-5-1` 与 `2.1.260 claude-fable-5-1` 只在缺失时补
  `{"type":"adaptive","display":"updates"}`，不得覆盖客户端已有 thinking 字段。
- `2.1.257` Fable 5.1 beta 顺序必须使用画像常量，其中包含
  `server-side-fallback-2026-07-01` 和 `thinking-display-updates-2026-08-18`，且不包含
  `redact-thinking-2026-02-12`；Fable 5 保留 redact，但 fallback beta 也必须是
  `server-side-fallback-2026-07-01`。
- `2.1.260` Fable 5.1 在 `2.1.257` 画像基础上增加
  `per-turn-control-2026-07-01`；当前没有 `2.1.260 claude-fable-5` 证据，不能套用该画像。
- `2.1.220` Fable 顶层字段顺序为 `model,messages,system,tools,metadata,max_tokens,thinking,context_management,fallbacks,output_config,diagnostics,stream`；旧画像保留旧顺序。
- Fable 5/5.1 的 `fallbacks="default"` 必须发送给上游，并按上面的精确版本与模型规则
  参与 CCH；旧画像是否裁剪 fallback 由各自 `CchProfile` 决定。

`2.1.260` 通用与 Haiku body 契约：

- Opus 5、Sonnet 5 主请求缺少 thinking 时补
  `{"type":"adaptive","display":"updates"}`，`max_tokens` 缺失时补 `64000`，并使用
  `output_config.effort=max`；不覆盖客户端已有 thinking、max_tokens 或 effort。
- Haiku main 缺少 thinking 时补
  `{"budget_tokens":31999,"type":"enabled","display":"updates"}`，`max_tokens` 缺失时
  补 `32000`，不主动添加 `output_config`。
- thinking 字段顺序必须保持 Opus/Sonnet/Fable 5.1 为 `type,display`，Haiku 为
  `budget_tokens,type,display`；主请求顶层字段顺序继续保持抓包顺序。

Haiku 2.1.257 子画像契约：

- 只在模型 ID 包含 `haiku` 时分类；probe 为 `tools` 空、`max_tokens=1`、非流式。
- title 为 `tools` 空、`max_tokens=32000`，并命中结构化 title schema 或历史 title
  prompt marker。结构化分支还要求流式、`thinking.type=disabled`，且
  `output_config.format` 的任一嵌套对象同时声明唯一 required `title` 和
  `properties.title`。
- 为兼容已存在的 title 变体，历史 prompt marker 分支不额外强制 `stream=true`，schema
  检测也保留递归查找；这是已接受的兼容宽度，不能在缺少新抓包回归时擅自收窄。
- non-stream aux 为 `tools` 空、`max_tokens=1024`、非流式；其余 Haiku 请求归为 main。
- main 有 `diagnostics` 时使用完整 Haiku main beta；无 `diagnostics` 时省略
  `claude-code-20250219`；probe、title、non-stream aux 各使用画像中的独立窄 beta。

标题可选 beta 契约：

- 2.1.257/2.1.260 的标题基础窄画像之外，只保留客户端已携带的
  `server-side-fallback-2026-07-01`、`fallback-credit-2026-06-01`；按此顺序去重，
  插入 `cache-diagnosis-2026-04-07` 前。没有携带时不主动开启。
- token 按逗号拆分、去空白后精确匹配；旧日期、相似后缀和父模型的其他 beta 不合入。
- 两种客户端入口共用最终规范化。旧画像的可选列表为空；probe 不保留这些 token。

后台 UA/beta 契约：

- 2.1.257/2.1.260 使用 `EndpointHeaderProfile::ClaudeCode21257`。下表的 12 类
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

Bootstrap 契约：

- `/api/claude_cli/bootstrap` response 可能是 gzip；改写前必须按 `Content-Encoding` 解码 JSON。
- 改写后的响应返回未压缩 JSON 时必须移除或重算 `Content-Encoding`、`Content-Length`、`Transfer-Encoding`，避免客户端按旧压缩头解释。
- Fable 能力由全局设置控制：
  - `bootstrap_model_options_mode=passthrough`：不改上游。
  - `configured`：可按版本画像注入 `client_data.cedar_basin`、
    `client_data.cedar_lagoon`、`additional_model_options`；cwk 必须按精确模型 ID 选择，
    不能只按 Fable/Opus family 选择。
  - `2.1.220` 的 Fable query 使用 `cwk_cfg_key="marigold"`，Opus 5 query 使用
    `cwk_cfg_key="belladonna"`。
  - `2.1.257` configured 默认模型选项为 `claude-fable-5-1[1m]`，
    `claude-fable-5` 使用 `marigold`，`claude-fable-5-1` 使用 `sorrel`，Opus 5 使用
    `belladonna`，`client_data.cedar_basin="2027-08-31"`。
  - `2.1.260` configured 继续使用 `claude-fable-5-1[1m]` 和
    `client_data.cedar_basin="2027-08-31"`；Opus 5=`belladonna`、Sonnet 5=`pewter`、
    Fable 5.1=`sorrel`、Haiku=`null`。当前没有 `2.1.260 Fable 5` cwk 证据。
  - `hide_fable`：隐藏 Fable 入口并仅清空所选精确模型对应的 Fable key，不得误清除
    Opus 5 的合法 `belladonna` 或 Sonnet 5 的合法 `pewter`。

`/api/hello` 边界契约：

- cc2api 必须在管理路由和鉴权 fallback 之前注册公开的 `GET/HEAD /api/hello`。
- GET 返回精确 JSON `{"message": "hello"}`；HEAD 返回相同 representation 的 `Content-Type` 和 `Content-Length: 20`，但 body 必须为空。
- 该端点是无状态连通性端点，不读取 gateway token，不选择账号，不占用 RPM/并发，不生成 telemetry，也不代理到上游。
- Claude Code `2.1.220` 的 hello 预检固定访问 `https://api.anthropic.com/api/hello`，不使用 `ANTHROPIC_BASE_URL`；模型请求才使用配置的 base URL。
- 因此当前不得为 new-api 添加同名本地响应、渠道选择或故障转移。只有后续版本抓包证明 hello 开始使用 `ANTHROPIC_BASE_URL` 时，才重新评估透传策略。
- session hello 代理探测的 UA 必须来自账号所选版本画像：2.1.260 与 2.1.257 使用
  `Bun/1.4.1`，2.1.220 回滚画像继续使用 `Bun/1.4.0`。

Telemetry 契约：

- `env.version`、`env.version_base`、`env.build_time` 必须跟默认版本画像一致。
- `model`、`preNormalizedModel`、`betas` 应来自最终请求 profile。
- `2.1.260` 继续使用既有 `ClaudeCode2185` telemetry shape；只迁移 env、build time 和
  UA，不因版本号新建 shape。
- `tengu_api_query` / `tengu_api_success` 等 request 事件的 `betas` 使用最终 message
  profile；普通启动和内部事件使用独立的窄 base beta，允许继续包含
  `redact-thinking-2026-02-12`。message beta 去掉 redact 时，不能同步改写 telemetry
  base beta。
- 非 Opus 启动时，在模型解析前短暂出现默认 `claude-opus-5[1m]` telemetry 不代表 wire
  主模型变化；以最终 request 事件和 `/v1/messages` 为准。
- `flags=model` 只表示 CLI 使用了一次性 `--model` 覆盖，不是 Fable 协议字段；不要因为模型是 Fable 就无条件写入。

账号迁移契约：

- 启动迁移必须把已有账号 `canonical_env.version/version_base/build_time/node_version` 更新到当前默认画像。
- 启动迁移必须同时迁移旧默认 settings 组合：当 `settings.claude_code_version_profile` 仍是上一个默认 profile，且 `settings.allowed_claude_code_versions` 仍是对应旧默认范围时，必须把二者升级到当前默认画像。
- 显式回滚 profile 只能在管理员自定义过 `allowed_claude_code_versions` 时保留；否则旧默认 profile 会让远程老库继续发送旧 UA / env 画像。
- `allow_system_role_models` 默认包含 `claude-fable-5-1`；一次性迁移必须按逗号列表精确
  去重后追加，并保留管理员自定义模型。
- `bootstrap_additional_model_options` 只在仍等于旧 Fable 5 默认 JSON 时迁移到 Fable
  5.1 默认值；自定义 JSON 保留。
- 不迁移 `allow_1m_models`、`rewrite_disabled_thinking_models` 或
  `intercept_assistant_prefill_models`。
- 远程部署后必须查 DB 版本分布，不能只依赖日志判断。

流式超时诊断契约：

- `stable_upstream_stream` 必须接收脱敏后的 upstream request ID，优先取 `request-id`，
  再取 `x-request-id`；超过 128 字符或包含非 `[A-Za-z0-9_.-]` 字符时只记录短 SHA256。
- `chunk_count=0` 超时记录 `upstream_first_byte_timeout`，错误文本为
  `upstream first byte timeout`；已收到真实 chunk 后超时记录
  `upstream_stream_idle_timeout`，错误文本为 `upstream stream idle timeout`。
- 两类日志都记录 account、upstream request ID、`wait_ms`、`chunk_count` 和
  `max_gap_ms`，不得记录请求正文、Authorization、Cookie 或账号邮箱。
- keepalive 只能在 `first_chunk_seen=true` 后注入，不能用伪造 SSE 掩盖上游首字节卡死，
  也不能重置真实上游 chunk 的静默超时。

### 4. Validation & Error Matrix

| 条件 | 期望 |
|------|------|
| 新版本抓包 CCH 不命中旧 seed | 先尝试输入规范化差异；只有多组样本都不命中时再逆向 seed |
| `cc_version` 主请求按第一个 text block 计算不命中 | 检查首条 user message 是否有多个 text block；按最后一个 text block 复算 |
| Fable 带 `[1m]` 时 beta 顺序与抓包不同 | 先按目标版本抓包判断是否应有 `context-1m-2025-08-07`；若应有，再整理到 `oauth` 后面 |
| 2.1.257 Fable 5.1 CCH 不命中 | 确认清空 `model`、删除 `max_tokens`，但保留 top-level `fallbacks="default"` |
| 2.1.257 Fable 5 CCH 不命中 | 确认 fallback 是字符串 `"default"`、beta 使用 `server-side-fallback-2026-07-01`，并保留 fallback 参与 CCH |
| 2.1.260 Fable 5.1 CCH 不命中 | 保留 `fallbacks="default"`；不得沿用旧的“所有模型删除 fallback”裁剪 |
| Fable 5.1 被套用 Fable 5 fallback/beta | 检查 `RequestProfile::fable_model` 是否按精确模型 ID 命中，不能使用 family 前缀选择 wire 画像 |
| 2.1.260 主请求缺少 thinking display | 按精确模型补 display；Haiku 还必须保留 `budget_tokens=31999` 和 `type=enabled` |
| 未观察 Haiku main 命中 2.1.260 Haiku beta | 新画像存在精确 `main_models` 时检查 `RequestProfile::main_model(model_id)`；未命中则回退版本级通用 beta |
| bootstrap Sonnet 5 没有 `pewter` | 检查 cwk 是否按精确模型映射，不能只维护 Fable/Opus 两个 family key |
| message beta 更新后普通 telemetry 丢失 redact | 将 base beta 与最终 message beta 分开维护，request 事件显式覆盖 |
| Haiku title 分类出现历史变体 | 保留结构化 schema 和旧 prompt marker 两条路径；没有新抓包证据时不收窄旧兼容分支 |
| 257/260 标题携带合法 fallback token | 仅保留已携带白名单 token，按抓包顺序放在 cache-diagnosis 前 |
| 标题未携带 fallback 或只有相似未知 token | 输出基础窄 beta，不主动开启 fallback |
| 已知 worker/presence/quota 路径携带主模型 beta | 输出端点专用 UA，删除 anthropic-beta |
| 未知后台子路径或旧版本画像 | 保留既有处理，不能用宽泛前缀匹配扩大修正范围 |
| 上游返回 200 headers 后一直无 SSE body | 等待历史 upstream idle timeout；记录 `upstream_first_byte_timeout`，不要提前注入 keepalive |
| 已收到 SSE chunk 后长时间静默 | 记录 `upstream_stream_idle_timeout`；keepalive 可维持下游连接，但不得重置上游 idle timeout |
| bootstrap response 有 gzip | 先解码再改 JSON，返回时修正压缩/长度相关 header |
| 未携带 token 请求 `GET/HEAD /api/hello` | 返回 200；HEAD body 为空且 `Content-Length=20` |
| 未携带 token 请求其他 fallback 路径 | 保持原 gateway token 鉴权，不得因 hello 公开而放宽 |
| 讨论让 new-api 透传 hello | 先用目标版本探针验证是否使用 `ANTHROPIC_BASE_URL`；固定官方域名时不新增路由 |
| 老库保留旧默认 `claude_code_version_profile` | 若 `allowed_claude_code_versions` 也是旧默认范围，迁移 profile 和 allowed range 到当前默认；若 allowed range 是管理员自定义值，则保留显式回滚 |
| 远程部署后账号仍是旧版本 | 检查迁移是否执行；直接查 volume 内 SQLite/Postgres 的 `canonical_env` |
| 抓包分析需要保存到仓库 | 禁止提交完整 `http_capture.jsonl`、token、Cookie、Authorization、邮箱、完整 prompt/响应正文 |

### 5. Good/Base/Bad Cases

**Good**：升级版本前先收集 baseline 和目标版本的 Opus/Fable/Haiku 抓包，离线复算 `cc_version` 与 CCH，确认 beta 顺序，再改 profile 和测试。

**Good**：Fable 5 与 Fable 5.1 使用两个精确子画像，只在共享周配额判断中把已知 ID 和
`[suffix]` 形式归到 `seven_day_fable`。

**Good**：Haiku probe/title/non-stream aux 继续使用已验证的请求类型分类；Haiku main 在
新画像中只有精确模型 ID 命中时才使用新 beta，未知 Haiku 回退版本级通用画像。

**Good**：抓包分析同时核对 raw flow 与 JSONL/index；结构化索引完整不等于没有未完成的
零正文 message 或后台长连接尝试。

**Good**：标题可选 token 的三种已观察组合由脱敏 fixture 固定预期；后台端点同时断言
UA 和 beta，覆盖两种入口及无 beta 的删除行为。

**Base**：只升级一个 patch 版本，也必须至少验证 `/v1/messages` header、body keys、billing header、bootstrap 和 telemetry metadata 是否变化。

**Bad**：只把 `DEFAULT_CLAUDE_CODE_VERSION` 改成新版本，未同步 `User-Agent`、账号迁移、CCH 输入 profile 和 beta 顺序。

**Bad**：只迁移 `allowed_claude_code_versions`，但没有把旧默认 `claude_code_version_profile` 迁到新默认，导致启动时继续按旧 profile 刷账号 env。

**Bad**：看到 Fable 抓包里有 `flags=model`，就把它硬编码成所有 Fable telemetry 字段。

**Bad**：把 bootstrap cwk 按 Fable family 合并，导致 2.1.257 Fable 5 的 `marigold`
被 Fable 5.1 的 `sorrel` 覆盖，或漏掉 2.1.260 Sonnet 5 的 `pewter`。

**Bad**：把 `context-1m-2025-08-07` 放进 Fable 必需 beta，导致无 1M 设置时也开启 1M beta。

**Bad**：为了消除理论误判，在没有覆盖历史 title 变体的抓包和测试时收窄 Haiku 兼容
marker，导致原有标题生成请求落回通用 beta。

**Bad**：看到模型 ID 包含 `haiku` 就给所有 Haiku main 套用最新 beta，导致未观察模型
获得新 beta，却没有对应的 thinking、body 和 CCH 子画像。

**Bad**：把 200 response headers 当成流已成功；没有首个 SSE chunk 时仍可能在客户端
watchdog 前后报 `No response from API`。

**Bad**：因为模型请求链路是 `Claude Code -> new-api -> cc2api`，就假设 hello 也会使用同一 base URL，并在 new-api 中臆造渠道路由。

### 6. Tests Required

- `cargo fmt --check`
- `cargo test`
- `cargo test cch`
- 定向测试：
  - `cc_version_suffix_uses_string_indices`
  - `cc_version_suffix_source_uses_last_user_text_block`
  - `fable_messages_headers_use_fallback_beta_without_context_1m`
  - `fable_context_1m_beta_keeps_claude_code_order_when_allowed`
  - 2.1.260 Opus/Sonnet/Fable 5.1 使用 64000、adaptive display updates 和各自精确
    beta；Haiku 使用 32000、budget 31999、enabled display updates 且无 output_config
  - 2.1.260 Fable 5.1 使用 `fallbacks="default"`、per-turn beta，2.1.220 不识别该画像
  - 2.1.257 CCH 对 Fable 5 与 Fable 5.1 保留 top-level fallback，对其他模型删除
    fallback；2.1.260 对 Fable 5.1 保留 fallback
  - Haiku probe、结构化/旧 marker title、main 有无 diagnostics、non-stream aux 的 beta
    分类；保留兼容宽度的反例必须有回归断言；另需断言未观察 Haiku main 在存在精确
    `main_models` 的新画像中回退版本级通用 beta
  - `claude-code-2.1.260-header-compat.json`：标题基础/credit/server-side+credit 三种变体，
    重复、乱序、未知 token；257/260 两种入口一致，旧画像和 probe 保持窄集合
  - 后台 12 类路径逐项核对 UA/beta，传入主模型 beta 不得污染无 beta 端点；
    相似未知路径、空 session、尾斜杠和旧画像保持既有行为
  - Fable 5/5.1 与 `[suffix]` 命中 `seven_day_fable`，相似 preview 模型不命中
  - bootstrap 按精确模型断言 2.1.257 Fable 5=`marigold`、Fable 5.1=`sorrel`，以及
    2.1.260 Opus 5=`belladonna`、Sonnet 5=`pewter`、Fable 5.1=`sorrel`、Haiku=`null`
  - system-role 和 bootstrap 默认迁移只追加/替换历史默认，三个明确不迁移列表保持原值
  - 首字节 timeout、首 chunk 后 idle timeout、首 chunk 前无 keepalive、request ID 脱敏
  - bootstrap gzip 解码和 configured/hide_fable 行为
  - assembled Router 中无 token 的 GET/HEAD hello 返回 200，HEAD body 为空且长度为 20，其他 fallback 路径仍返回 401
  - telemetry 中 base beta 与 request beta 分离，Fable `betas`、`model` 正确，且不无条件
    写 `flags=model`
  - TokenTester 按账号选中画像生成 2.1.260、2.1.257、2.1.220 和旧回滚 profile 的 UA、
    Stainless package/runtime 和 beta
  - 旧默认 `claude_code_version_profile` + 旧默认 `allowed_claude_code_versions` 会升级到当前默认
  - 自定义 `allowed_claude_code_versions` 下的旧 profile 作为显式回滚保留
- 抓包回归：
  - 169 baseline CCH 命中旧完整 body 规则。
  - 172 Opus CCH 命中 `model + max_tokens` 排除规则。
  - 172 Fable CCH 命中 `model + max_tokens + fallbacks` 排除规则。
  - 257 Opus、Fable 5、Fable 5.1、Haiku 样本的 `cc_version` 与 CCH 全量命中；两个
    Fable 精确模型的 `fallbacks="default"` 都保留参与 hash。
  - 260 Opus、Sonnet、Fable 5.1、Haiku 共 117 条 billing 样本的 `cc_version` 与 CCH
    全量命中；删除 Fable 5.1 fallback 的错误算法必须全量不命中该模型样本。
- Fable `[1m]` 抓包 beta 是否包含 `context-1m-2025-08-07`、以及包含时的顺序，与目标版本代码输出完全一致。
- 远程部署验收：
  - `docker compose pull` 后必须 `up -d --force-recreate`。
  - `curl http://127.0.0.1:<port>/` 返回 200。
  - DB 中 `accounts.canonical_env.version/version_base/build_time` 分布全部为目标默认值。

### 7. Wrong vs Correct

#### Wrong: 标题精确画像始终删除全部客户端可选 beta

```text
标题携带 fallback-credit-2026-06-01 -> 仅输出固定基础 beta
```

#### Correct: 标题基础画像加版本化的已携带白名单

```text
标题携带 fallback-credit-2026-06-01 -> 基础 beta + credit（放在 cache-diagnosis 前）
标题未携带可选 token -> 基础 beta
```

#### Wrong: `cc_version` 固定取第一个 text block

```rust
for item in arr {
    if let Some(text) = item.get("text").and_then(|t| t.as_str()) {
        return text.to_string();
    }
}
```

这样会取到 Claude Code 注入的环境上下文 block，主请求后缀会和抓包不一致。

#### Correct: 对多 text block 取最后一个 prompt block

```rust
if let Some(text) = arr
    .iter()
    .rev()
    .find_map(|item| item.get("text").and_then(|t| t.as_str()))
{
    return text.to_string();
}
```

#### Wrong: 把客户端 1M beta 追加到末尾

```text
claude-code-20250219,oauth-2025-04-20,...,cache-diagnosis-2026-04-07,context-1m-2025-08-07
```

#### Correct: 按抓包把 1M beta 放到 oauth 后

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,...
```

#### Wrong: 用 Fable family 前缀选择 wire 画像

```rust
if model.starts_with("claude-fable-") {
    apply_fable_5_profile(body);
}
```

这会把 `claude-fable-5-1` 错写成 Fable 5 的 fallback、beta 和 CCH 输入。

#### Correct: 版本画像内按精确模型 ID 查找

```rust
if let Some(fable) = request_profile.fable_model(model) {
    apply_fable_profile(body, fable);
}
```

family 判断只用于已确认共享的 `seven_day_fable` 配额；wire profile 仍由精确 ID 决定。

#### Wrong: Haiku main 只按 family 选择最新 beta

```rust
if model_id.contains("haiku") {
    return request_profile.haiku_main_beta_tokens;
}
```

这会让未抓包的 Haiku 模型获得最新 beta，但其它主请求字段仍走通用画像。

#### Correct: 新画像的 Haiku main 先精确命中

```rust
if let Some(main) = request_profile.main_model(model_id) {
    return main.message_beta_tokens;
}
return request_profile.message_beta_tokens;
```

probe、title 和 non-stream aux 继续走各自已验证的独立窄画像；旧画像没有精确主模型表时
保留历史兼容行为。

#### Wrong: 假设 hello 跟随模型 base URL

```text
Claude Code -> ANTHROPIC_BASE_URL -> new-api -> /api/hello 渠道选择
```

#### Correct: 先按目标版本验证真实请求边界

```text
Claude Code 2.1.220 hello -> https://api.anthropic.com/api/hello
Claude Code 2.1.220 messages -> ANTHROPIC_BASE_URL -> new-api -> cc2api
```

---

## Scenario: Auto Mode classifier 版本化协议

### 1. Scope / Trigger

- Trigger：修改 `GatewayService` 对 Claude Code Auto Mode classifier 的识别条件、本地拦截顺序、Legacy Block / Severity 协议选择或 mock response 时适用。
- 目标：兼容新旧 Claude Code classifier，同时避免被审计 transcript 中的 XML 示例污染协议选择。

### 2. Signatures

- 检测入口：`detect_auto_mode_classifier_request(path, body, client_type) -> Option<WarmupInterceptType>`。
- 协议入口：`auto_mode_classifier_protocol(body) -> Option<AutoModeClassifierProtocol>`。
- Stage 1：`max_tokens` 在 `64..=2304`；Stage 2：`max_tokens` 在 `4096..=8192`。
- 公共请求特征：Claude Code、非流 `/v1/messages`、最后一条消息为 `user`、最后一条消息包含闭合的 `<transcript>...</transcript>`。

### 3. Contracts

| 协议 | 可信输出格式 | `mock_allow` | `mock_block` |
|------|--------------|--------------|--------------|
| Legacy Block | system 或 transcript 外指令同时定义 `<block>yes</block>` 与 `<block>no</block>` | `<block>no</block>` | `<block>yes</block><reason>blocked by local policy</reason>` |
| Severity | system 或 transcript 外指令定义完整 `<severity>...</severity>` 格式 | `<severity>0</severity>` | `<severity>100</severity>` |

- 协议只能由 `system` 或最后一条 user message 中 transcript 外的 classifier 指令确定；被审计 transcript 内的标签属于不可信内容。
- 不依赖整句 prompt 精确匹配，可信区域只要求协议自身的完整输出标记，避免文案微调导致漏命中。
- 可信区域同时出现两套完整协议、协议标记不完整或 transcript 未闭合时，必须视为非强命中并透传上游。
- 本地 mock response 必须保持 Anthropic message JSON 形状，`cache_creation_input_tokens` 与 `cache_read_input_tokens` 均为 `0`，并在账号选择、RPM 和并发槽位获取前返回。

### 4. Validation & Error Matrix

| 条件 | 期望行为 |
|------|----------|
| Legacy Block system，transcript 内出现 Severity 示例 | 仍选择 Legacy Block |
| Severity system，transcript 内出现 Legacy Block 示例 | 仍选择 Severity |
| system 无协议，只有 transcript 内存在协议标签 | 不命中 classifier，透传上游 |
| transcript 后的可信指令定义单一协议 | 按该协议命中，不要求 system 精确文案 |
| 可信区域同时定义 Legacy Block 和 Severity | 不猜测协议，透传上游 |
| transcript 缺少开始或结束标签 | 不命中 classifier，透传上游 |

### 5. Good/Base/Bad Cases

- Good：旧版 Block classifier 的 transcript 正在讨论 `<severity>0</severity>`，仍返回 `<block>no</block>`。
- Good：新版 Severity classifier 的 transcript 包含旧版 block 示例，仍返回 `<severity>0</severity>`。
- Base：可信 system 或 transcript 后置指令只定义一套完整协议，按 Stage token 范围正常识别。
- Bad：扫描 `request_text_items(body)` 的全部文本并让 Severity 固定优先，会让用户内容改变本地安全响应协议。
- Bad：硬编码完整 system prompt 文案，会因 Claude Code 轻微改词而漏掉真实 classifier。

### 6. Tests Required

- `auto_mode_classifier_detects_severity_stage1` / `auto_mode_classifier_detects_severity_stage2`：新版协议仍覆盖两个 Stage。
- `auto_mode_classifier_detects_protocol_from_post_transcript_instruction`：system 无协议标记时，可信后置指令仍可命中。
- `auto_mode_classifier_uses_block_protocol_when_transcript_mentions_severity`：transcript 不覆盖旧版协议。
- `auto_mode_classifier_uses_severity_protocol_when_transcript_mentions_block`：transcript 不覆盖新版协议。
- `auto_mode_classifier_ignores_protocol_markers_only_inside_transcript`：普通用户内容不能制造 classifier 命中。
- `auto_mode_classifier_ignores_conflicting_trusted_protocol_markers`：可信区域冲突时失败开放。
- 完整验证运行 `cargo fmt --check`、`cargo test`、`cargo test cch`。

### 7. Wrong vs Correct

#### Wrong: 从全部请求文本猜测协议

```rust
for text in request_text_items(body) {
    has_severity |= text.contains("<severity>");
}
if has_severity {
    return Some(AutoModeClassifierProtocol::Severity);
}
```

transcript 是被审计的用户输入，里面的示例标签不能决定本地 mock response 格式。

#### Correct: 只读取可信 classifier 指令

```rust
for text in system_text_items(body) {
    observe_protocol_markers(text);
}
let last_message_content = body
    .get("messages")
    .and_then(|messages| messages.as_array())
    .and_then(|messages| messages.last())
    .and_then(|message| message.get("content"));
let mut inside_transcript = false;
for text in content_text_items(last_message_content) {
    let mut remaining = text;
    loop {
        if inside_transcript {
            let Some(close_index) = remaining.find("</transcript>") else {
                break;
            };
            inside_transcript = false;
            remaining = &remaining[close_index + "</transcript>".len()..];
            continue;
        }
        let Some(open_index) = remaining.find("<transcript>") else {
            observe_protocol_markers(remaining);
            break;
        };
        observe_protocol_markers(&remaining[..open_index]);
        inside_transcript = true;
        remaining = &remaining[open_index + "<transcript>".len()..];
    }
}
match (
    has_block_yes && has_block_no,
    has_severity_open && has_severity_close,
) {
    (true, false) => Some(AutoModeClassifierProtocol::Block),
    (false, true) => Some(AutoModeClassifierProtocol::Severity),
    _ => None,
}
```

协议冲突或证据不足时透传上游，既不误拦截，也不向客户端返回错误协议。

---

## Common Mistakes

| 反模式 | 现象 | 怎么改 |
|--------|------|--------|
| 只改版本常量 | 请求 UA、账号 env、telemetry 或 access policy 仍停旧版本 | 搜索旧版本号并逐处确认 |
| 只看 CCH 不看 `cc_version` | CCH 命中但 billing header 后缀不真实 | 对每条主请求复算 suffix |
| 重新序列化 body 再算 CCH | 字段顺序或转义变化导致 hash 偏移 | 在最终 body 字节上做 top-level 裁剪 |
| Fable beta 无条件注入 1M | 不允许 1M 的账号也带 `context-1m` | 让客户端/白名单决定 1M |
| 只迁移 allowed range | 老库仍读取旧 `claude_code_version_profile`，账号 env 被刷新回旧版本 | 旧默认 profile setting 和旧默认 allowed range 必须成对迁移 |
| 部署后只看容器 Up | 账号仍可能停旧 `canonical_env` | 查 DB 版本分布 |

---

## Scenario: Claude Fast Mode 账号级透传控制

### 1. Scope / Trigger

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

**Bad**：bench 每次同步都更新 `allow_fast_mode=false`，覆盖管理员在 cc2api 中的显式放行。

**Bad**：使用 `replace("fast-mode-2026-02-01", "")`，误伤前后缀相似 token 或留下无效分隔符。

### 6. Tests Required

- Rewriter：默认删除、显式允许、精确 token 匹配、未携带时不注入、与 `context-1m` 组合后其他客户端 token 顺序稳定。
- Count tokens：默认删除与显式允许各一例，并断言 `token-counting-2024-11-01` 保留。
- Store/DB：新账号默认 `false`、旧 SQLite 行迁移后为 `0`、更新为 `true` 后读取和列表返回正确。
- 管理 API：创建 payload 缺省时响应为 `false`，PUT 更新为 `true` 后 GET/list 往返一致。
- 前端：`cd cc2api/web && npm run build`，并确认新建默认“禁止”、编辑回填和保存 payload 一致。
- bench：首次创建 payload 明确包含 `allow_fast_mode=false`；匹配既有账号和重复同步不调用创建或账号配置更新接口。
- 回归门禁：`cargo fmt --check`、`cargo test`、`cargo test cch`、orchestrator 单元测试。

### 7. Wrong vs Correct

#### Wrong: 账号允许后主动注入 Fast Mode

```rust
if account.allow_fast_mode {
    required_beta.push_str(",fast-mode-2026-02-01");
}
```

#### Correct: 只过滤或保留客户端已有 token

```rust
let filtered = if account.allow_fast_mode {
    incoming_beta.to_string()
} else {
    strip_beta_token(incoming_beta, "fast-mode-2026-02-01")
};
```

#### Wrong: bench 同步既有账号时重置管理员配置

```python
cc2api_client.update_account(account_id, {"allow_fast_mode": False})
```

#### Correct: 只在首次创建时显式关闭

```python
cc2api_client.create_account({
    "email": profile["email"],
    "allow_fast_mode": False,
})
```

---

## Scenario: Claude Code currentDate 风险治理

### 1. Scope / Trigger

- Trigger: Claude Code 在非官方 `ANTHROPIC_BASE_URL`、代理、网关或中国时区画像下改变自动上下文中的 currentDate 标记。
- 该场景属于跨层契约：`/v1/messages` body 改写、settings、管理 API、前端设置页、telemetry 清洗和日志策略必须一致。
- 默认行为必须低风险：只观测和 telemetry 清洗；只有管理员显式选择 `normalize` 时才改写请求体。

### 2. Signatures

关键代码入口：

```text
src/service/rewriter.rs
src/service/gateway.rs
src/service/telemetry.rs
src/handler/router.rs
src/store/settings_store.rs
src/store/db.rs
web/src/components/Settings.vue
```

关键 setting：

```text
settings.claude_code_context_sanitizer_mode = off | report_only | normalize
```

### 3. Contracts

请求体治理契约：

- 仅对 `ClientType::ClaudeCode` 的 `/v1/messages` 改写链路生效；普通 API 客户端不触发。
- 只扫描 Claude Code 自动上下文位置：`system` text、`system[] .text`、带上下文 marker 的 `messages[].content` text、多 text block 中首个上下文 block。
- `report_only` 只记录脱敏摘要，不修改 body；`normalize` 才把命中句式统一为 `Today's date is YYYY-MM-DD.`。
- 规范化必须发生在最终 CCH / `cc_version` 刷新前，避免 hash 和 billing header 基于旧文本计算。
- 支持日期分隔符 `-` 和 `/`，但同一句中年月、月日分隔符必须一致。

currentDate 撇号契约：

```text
Today['\u{2019}\u{02BC}\u{02B9}\u{2032}]s date is YYYY[-/]MM[-/]DD.
```

已知变体：

| 字符 | 码点 | 日志类别 |
|------|------|----------|
| `'` | U+0027 | `ascii` |
| `’` | U+2019 | `right_single_quote` |
| `ʼ` | U+02BC | `modifier_letter_apostrophe` |
| `ʹ` | U+02B9 | `modifier_letter_prime` |
| `′` | U+2032 | `prime` |

日志和 telemetry 契约：

- currentDate finding 日志只能包含 `mode`、`action`、`path`、`date_separator`、`apostrophe_variant`、`text_len`、短 hash、`client_type`，禁止输出完整 prompt、system 或 request body。
- telemetry sanitizer 必须清洗非官方 `base_url` / `gateway` / `proxy` key/value 痕迹。
- 官方 Anthropic host 值允许保留：`anthropic.com`、`api.anthropic.com`、`claude.ai`、`console.anthropic.com` 及其子域。

### 4. Validation & Error Matrix

| 条件 | 期望 |
|------|------|
| `claude_code_context_sanitizer_mode` 是未知值 | `/admin/settings` PUT 返回 BadRequest，不刷新热路径 |
| mode=`off` | 不扫描、不打 finding 日志、不改写 body |
| mode=`report_only` 且命中 currentDate | 输出脱敏 warning，body 字节语义不变 |
| mode=`normalize` 且命中 `Todayʹs date is 2026/06/30.` | 改为 `Today's date is 2026-06-30.` |
| 非 Claude Code 客户端发送同样文本 | 不触发扫描或规范化 |
| 普通用户正文单 text block 包含 `Today's date is ...` | 不改写，避免误伤真实用户内容 |
| telemetry 中出现 `gatewayHost=https://internal.example` | 删除该字段 |
| telemetry 中出现 `baseUrl=https://api.anthropic.com` | 保留该字段 |

### 5. Good/Base/Bad Cases

**Good**：默认 `report_only` 上线，先通过脱敏日志确认 `date_separator` 和 `apostrophe_variant` 分布，再由管理员显式打开 `normalize`。

**Base**：中国时区下出现 `2026/06/30` 时，只在 `normalize` 模式改为 `2026-06-30`。

**Bad**：把所有用户消息中的 `Today's date is` 都替换，导致真实用户内容被静默修改。

**Bad**：只覆盖 `′` U+2032，漏掉 Claude Code 实际可能使用的 `ʹ` U+02B9。

**Bad**：在日志里输出完整 system prompt 或 request body，泄露工作目录、环境、token 或用户正文。

### 6. Tests Required

- `cargo fmt --check`
- `cargo test context_sanitizer`
- `cargo test telemetry_sanitizer`
- `cargo test`
- 涉及设置页时运行 `cd cc2api/web && npm run build`
- 断言点：
  - 默认 settings 返回 `report_only`。
  - `report_only` 不修改 body。
  - `normalize` 覆盖 `'`、`’`、`ʼ`、`ʹ`、`′` 与 `YYYY/MM/DD`。
  - 规范化后 CCH 占位符被最终刷新。
  - API 客户端和普通用户正文不被误改。
  - telemetry 清洗非官方 base URL / gateway / proxy，同时保留官方 Anthropic host。

### 7. Wrong vs Correct

#### Wrong: 只匹配 ASCII 撇号

```text
Today's date is 2026/06/30.
```

这样会漏掉 `Todayʹs date is ...`，其中 `ʹ` 是 U+02B9，不是 U+2032。

#### Correct: 明确列出已知 Unicode 变体

```text
Today['\u{2019}\u{02BC}\u{02B9}\u{2032}]s date is YYYY[-/]MM[-/]DD.
```

#### Wrong: report_only 中改写请求体

```text
mode=report_only, action=normalize
```

#### Correct: report_only 只输出脱敏摘要

```text
mode=report_only, action=report_only, apostrophe_variant=modifier_letter_prime, date_separator=/
```

---

## Scenario: Claude Code 版本画像切换

### 1. Scope / Trigger

- Trigger: 新增或修改 `claude_code_version_profile` 可选版本，或让系统设置切换 Claude Code 版本特征。
- 本场景属于跨层契约：settings、账号 `canonical_env`、访问策略、请求重写、telemetry、前端 Settings 必须一起更新。
- 版本画像切换必须只允许内置 profile key，不能接受任意版本字符串拼装请求特征。

### 2. Signatures

关键代码入口：

```text
src/service/version_profile.rs
src/store/settings_store.rs
src/store/account_store.rs
src/service/account.rs
src/handler/router.rs
src/service/rewriter.rs
src/service/telemetry.rs
web/src/api.ts
web/src/components/Settings.vue
```

关键 setting：

```text
claude_code_version_profile=<profile key>
allowed_claude_code_versions=<profile.access_policy.allowed_claude_code_versions>
allowed_user_agents=<管理员自定义值，版本切换不得覆盖>
```

账号身份字段：

```json
{
  "version": "<profile.identity.version>",
  "version_base": "<profile.identity.version_base>",
  "build_time": "<profile.identity.build_time>"
}
```

### 3. Contracts

- `src/service/version_profile.rs` 是唯一画像注册表。新增版本必须声明 `identity`、`access_policy`、`request`、`billing`、`telemetry`、`endpoints` 子画像。
- `claude_code_version_profile` 保存时必须校验为内置 profile key；未知 key 返回 `BadRequest`，不能落库。
- 切换 profile 必须在同一事务中完成：
  - 写入 `settings.claude_code_version_profile`。
  - 强制覆盖 `settings.allowed_claude_code_versions` 为目标画像范围。
  - 批量覆盖所有账号 `canonical_env.version/version_base/build_time`。
- 切换 profile 不得覆盖 `allowed_user_agents`，该 setting 仍由管理员独立维护。
- 新账号创建必须读取当前 `claude_code_version_profile`，再把目标 `identity` 写入 `canonical_env`。
- 请求重写和 telemetry 必须从账号 `canonical_env.version` 映射到内置 profile；映射失败只能回退默认内置 profile，不能拼出未验证特征。
- 只提交 `claude_code_version_profile` 的 settings payload 时，也必须 reload access policy，因为后端会同步改写 `allowed_claude_code_versions`。
- 前端 Settings 保存成功后必须重新加载 settings，用后端强制覆盖后的版本范围作为只读回显。

### 4. Validation & Error Matrix

| 条件 | 期望 |
|------|------|
| settings 提交未知 `claude_code_version_profile` | 返回 `BadRequest`，不更新 settings 和账号 env |
| 只提交 `claude_code_version_profile` | 同步覆盖 `allowed_claude_code_versions` 并 reload access policy |
| 切换 profile 时存在自定义 `allowed_user_agents` | 原值保持不变 |
| 切换 profile 后已有账号仍保留旧 `canonical_env.version` | 视为失败，检查事务内账号批量更新 |
| 账号 env.version 不是内置版本 | 热路径回退默认 profile，避免组合未验证请求/telemetry 特征 |
| 新增 profile 只填版本号 | 视为不完整，必须补齐 request/billing/telemetry/endpoints 子画像和测试 |

### 5. Good/Base/Bad Cases

**Good**：新增 `2.1.xxx` 时先把抓包差异整理成 profile 子画像，补 settings 切换测试、账号 env 批量更新测试、rewriter/telemetry shape 测试，再开放前端选项。

**Base**：两个版本暂时共享 request/billing 子画像，也要在 profile 中显式声明共享字段，便于后续版本局部拆分。

**Bad**：在 `telemetry.rs` 或 `rewriter.rs` 里散落 `if version == "2.1.xxx"`，导致新增版本需要多处猜测。

**Bad**：允许管理员输入任意版本号，并用该字符串直接生成 UA、billing header 或 telemetry payload。

### 6. Tests Required

- profile registry：
  - profile key 唯一。
  - 默认 profile 存在。
  - 每个 profile 的 identity、access policy、telemetry UA、endpoint 字段非空。
- settings：
  - 未知 `claude_code_version_profile` 返回错误。
  - 切换 profile 后 settings 与所有账号 env 在同一事务结果中一致。
  - `allowed_claude_code_versions` 被强制覆盖，`allowed_user_agents` 保留。
  - profile-only payload 触发 access policy reload 的可观察行为。
- account：
  - 新账号使用当前 profile 的 `identity`。
- protocol：
  - rewriter 按账号 env.version 选择 UA、beta、billing/CCH 子画像。
  - telemetry 按 profile shape 切换 event logging 和 GrowthBook payload。

### 7. Wrong vs Correct

#### Wrong: 任意版本字符串直通

```rust
settings.insert("claude_code_version_profile".into(), user_input_version);
```

这会让请求和 telemetry 进入没有抓包验证的组合状态。

#### Correct: 只能选择内置画像

```rust
let profile = profile_for_key(&user_input_version)?;
settings.insert("claude_code_version_profile".into(), profile.key.to_string());
settings.insert(
    "allowed_claude_code_versions".into(),
    profile.access_policy.allowed_claude_code_versions.to_string(),
);
```

#### Wrong: 切版本时顺手覆盖 UA 白名单

```rust
settings.insert("allowed_user_agents".into(), profile_default_user_agents);
```

这样会覆盖管理员的独立安全策略。

#### Correct: 只覆盖 Claude Code 版本范围

```rust
settings.insert(
    "allowed_claude_code_versions".into(),
    profile.access_policy.allowed_claude_code_versions.to_string(),
);
```
