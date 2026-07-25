# Claude Code Profile Upgrade

> 记录 `cc2api` 升级 Claude Code 版本画像时必须执行的协议契约。目标是让未来从 `2.1.172` 升到新版本时，不再只改版本号而漏掉 CCH、`cc_version`、beta 顺序、bootstrap 和账号迁移。

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

`cc_version` 后缀契约：

- 算法：`sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`。
- 字符索引必须按 JavaScript UTF-16 code unit 语义。
- `messages[0].content` 是数组时，Claude Code 主请求可能先放环境上下文 text block，再放真实用户 prompt text block；后缀文本源应取首条 user message 的最后一个 text block，而不是第一个 text block。
- Haiku/title 这类只有一个 text block 的请求仍取唯一 text block。

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
- `2.1.156` / `2.1.169` / `2.1.172` seed 均为 `0x4D659218E32A3268`。
- `2.1.169`：在最终 body 字节上把真实 `cch=<5hex>` 替回 `cch=00000` 后计算，保留完整 body。
- `2.1.172`：在最终 body 字节上替回 `cch=00000` 后，再做 top-level 规范化：
  - `model` 字段保留 key 和空字符串值，排除原模型值。
  - 删除 top-level `max_tokens` 字段。
  - 删除 top-level `fallbacks` 字段。
- CCH 输入裁剪必须只作用 top-level JSON 字段，不能误删 tool schema、message content 或嵌套对象里的同名字段。
- 不要先 `serde_json` 反序列化再重新序列化后计算 CCH；字段顺序、转义和空格变化会改变结果。

Beta 顺序契约：

- `context-1m-2025-08-07` 不放进通用必需 beta；它由账号 `allow_1m_models` 和客户端传入 beta 共同决定。
- 当允许 1M 并保留 `context-1m-2025-08-07` 时，顺序必须整理为 `oauth-2025-04-20` 后、`interleaved-thinking-2025-05-14` 前。
- Fable 无 1M 主请求顺序：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

- Fable `[1m]` 的主请求画像必须按目标版本抓包判断，不能只从 CLI model 后缀推断：
  - `2.1.172` 抓包中，Fable `[1m]` 主请求包含 `context-1m-2025-08-07`，顺序如下。
  - `2.1.173` 抓包中，Fable `[1m]` 主请求不包含 `context-1m-2025-08-07`，只在 telemetry 启动配置里体现 `cli_flag=claude-fable-5[1m]`。
  - 账号 `allow_1m_models` 只控制客户端已有 `context-1m-2025-08-07` 是否透传，不应自动给 Fable 主请求注入 1M beta。

`2.1.172` Fable `[1m]` 主请求顺序：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Fable body 契约：

- `model=claude-fable-5`。
- `max_tokens=64000` 默认只在缺失时补齐，不覆盖用户已有值。
- `fallbacks` 必须来自选中的版本画像，只在缺失时补齐，不重复追加，不覆盖用户已有字段。
  - `2.1.220` 使用 `[{"model":"claude-opus-5"}]`。
  - `2.1.197` 及旧回滚画像保留 `[{"model":"claude-opus-4-8"}]`。
- `2.1.220` Fable 顶层字段顺序为 `model,messages,system,tools,metadata,max_tokens,thinking,context_management,fallbacks,output_config,diagnostics,stream`；旧画像保留旧顺序。
- `fallbacks` 必须发送给上游，但不参与 `2.1.172` CCH 输入。

Bootstrap 契约：

- `/api/claude_cli/bootstrap` response 可能是 gzip；改写前必须按 `Content-Encoding` 解码 JSON。
- 改写后的响应返回未压缩 JSON 时必须移除或重算 `Content-Encoding`、`Content-Length`、`Transfer-Encoding`，避免客户端按旧压缩头解释。
- Fable 能力由全局设置控制：
  - `bootstrap_model_options_mode=passthrough`：不改上游。
  - `configured`：可按版本画像注入 `client_data.cedar_basin`、`client_data.cedar_lagoon`、`additional_model_options`；2.1.220 的 Fable query 使用 `cwk_cfg_key="marigold"`，Opus 5 query 使用 `cwk_cfg_key="belladonna"`。
  - `hide_fable`：隐藏 Fable 入口并清空 `marigold`，但不得误清除 Opus 5 的合法 `belladonna`。

`/api/hello` 边界契约：

- cc2api 必须在管理路由和鉴权 fallback 之前注册公开的 `GET/HEAD /api/hello`。
- GET 返回精确 JSON `{"message": "hello"}`；HEAD 返回相同 representation 的 `Content-Type` 和 `Content-Length: 20`，但 body 必须为空。
- 该端点是无状态连通性端点，不读取 gateway token，不选择账号，不占用 RPM/并发，不生成 telemetry，也不代理到上游。
- Claude Code `2.1.220` 的 hello 预检固定访问 `https://api.anthropic.com/api/hello`，不使用 `ANTHROPIC_BASE_URL`；模型请求才使用配置的 base URL。
- 因此当前不得为 new-api 添加同名本地响应、渠道选择或故障转移。只有后续版本抓包证明 hello 开始使用 `ANTHROPIC_BASE_URL` 时，才重新评估透传策略。

Telemetry 契约：

- `env.version`、`env.version_base`、`env.build_time` 必须跟默认版本画像一致。
- `model`、`preNormalizedModel`、`betas` 应来自最终请求 profile。
- `flags=model` 只表示 CLI 使用了一次性 `--model` 覆盖，不是 Fable 协议字段；不要因为模型是 Fable 就无条件写入。

账号迁移契约：

- 启动迁移必须把已有账号 `canonical_env.version/version_base/build_time/node_version` 更新到当前默认画像。
- 启动迁移必须同时迁移旧默认 settings 组合：当 `settings.claude_code_version_profile` 仍是上一个默认 profile，且 `settings.allowed_claude_code_versions` 仍是对应旧默认范围时，必须把二者升级到当前默认画像。
- 显式回滚 profile 只能在管理员自定义过 `allowed_claude_code_versions` 时保留；否则旧默认 profile 会让远程老库继续发送旧 UA / env 画像。
- 远程部署后必须查 DB 版本分布，不能只依赖日志判断。

### 4. Validation & Error Matrix

| 条件 | 期望 |
|------|------|
| 新版本抓包 CCH 不命中旧 seed | 先尝试输入规范化差异；只有多组样本都不命中时再逆向 seed |
| `cc_version` 主请求按第一个 text block 计算不命中 | 检查首条 user message 是否有多个 text block；按最后一个 text block 复算 |
| Fable 带 `[1m]` 时 beta 顺序与抓包不同 | 先按目标版本抓包判断是否应有 `context-1m-2025-08-07`；若应有，再整理到 `oauth` 后面 |
| bootstrap response 有 gzip | 先解码再改 JSON，返回时修正压缩/长度相关 header |
| 未携带 token 请求 `GET/HEAD /api/hello` | 返回 200；HEAD body 为空且 `Content-Length=20` |
| 未携带 token 请求其他 fallback 路径 | 保持原 gateway token 鉴权，不得因 hello 公开而放宽 |
| 讨论让 new-api 透传 hello | 先用目标版本探针验证是否使用 `ANTHROPIC_BASE_URL`；固定官方域名时不新增路由 |
| 老库保留旧默认 `claude_code_version_profile` | 若 `allowed_claude_code_versions` 也是旧默认范围，迁移 profile 和 allowed range 到当前默认；若 allowed range 是管理员自定义值，则保留显式回滚 |
| 远程部署后账号仍是旧版本 | 检查迁移是否执行；直接查 volume 内 SQLite/Postgres 的 `canonical_env` |
| 抓包分析需要保存到仓库 | 禁止提交完整 `http_capture.jsonl`、token、Cookie、Authorization、邮箱、完整 prompt/响应正文 |

### 5. Good/Base/Bad Cases

**Good**：升级版本前先收集 baseline 和目标版本的 Opus/Fable/Haiku 抓包，离线复算 `cc_version` 与 CCH，确认 beta 顺序，再改 profile 和测试。

**Base**：只升级一个 patch 版本，也必须至少验证 `/v1/messages` header、body keys、billing header、bootstrap 和 telemetry metadata 是否变化。

**Bad**：只把 `DEFAULT_CLAUDE_CODE_VERSION` 改成新版本，未同步 `User-Agent`、账号迁移、CCH 输入 profile 和 beta 顺序。

**Bad**：只迁移 `allowed_claude_code_versions`，但没有把旧默认 `claude_code_version_profile` 迁到新默认，导致启动时继续按旧 profile 刷账号 env。

**Bad**：看到 Fable 抓包里有 `flags=model`，就把它硬编码成所有 Fable telemetry 字段。

**Bad**：把 `context-1m-2025-08-07` 放进 Fable 必需 beta，导致无 1M 设置时也开启 1M beta。

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
  - bootstrap gzip 解码和 configured/hide_fable 行为
  - assembled Router 中无 token 的 GET/HEAD hello 返回 200，HEAD body 为空且长度为 20，其他 fallback 路径仍返回 401
  - telemetry 中 Fable `betas`、`model`，以及不无条件写 `flags=model`
  - TokenTester 按账号选中画像生成 2.1.220/旧回滚 profile 的 UA、Stainless package/runtime 和 beta
  - 旧默认 `claude_code_version_profile` + 旧默认 `allowed_claude_code_versions` 会升级到当前默认
  - 自定义 `allowed_claude_code_versions` 下的旧 profile 作为显式回滚保留
- 抓包回归：
  - 169 baseline CCH 命中旧完整 body 规则。
  - 172 Opus CCH 命中 `model + max_tokens` 排除规则。
  - 172 Fable CCH 命中 `model + max_tokens + fallbacks` 排除规则。
- Fable `[1m]` 抓包 beta 是否包含 `context-1m-2025-08-07`、以及包含时的顺序，与目标版本代码输出完全一致。
- 远程部署验收：
  - `docker compose pull` 后必须 `up -d --force-recreate`。
  - `curl http://127.0.0.1:<port>/` 返回 200。
  - DB 中 `accounts.canonical_env.version/version_base/build_time` 分布全部为目标默认值。

### 7. Wrong vs Correct

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
