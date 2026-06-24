# Claude Code 2.1.187 抓包摘要（脱敏）

## Source

- 本地抓包目录：`data/flows/6-23/4144/c7e324fbb199/`
- 抓包文件：`http_capture.jsonl` 74 条 flow，另有 `capture_index.json`、`stats.jsonl` 和 `.flow` 原始文件。
- 只记录协议字段摘要，不记录完整 prompt、响应正文、token、Cookie、Authorization、邮箱、完整 UUID 或完整抓包。

## Endpoint Counts

- `POST /api/event_logging/v2/batch`：36 条
- `POST /v1/messages?beta=true`：25 条
- `HEAD /`：1 条
- `POST /api/eval/sdk-zAZezfDKGoZuXXKe`：1 条
- `GET /api/oauth/account/settings`：1 条
- `GET /api/claude_code_grove`：1 条
- `GET /api/claude_code_penguin_mode`：1 条
- `GET /api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8`：1 条
- `GET /v1/code/triggers`：1 条
- `GET /v1/mcp_servers?limit=1000`：1 条
- `GET /api/oauth/organizations/.../referral/eligibility?campaign=claude_code_guest_pass`：1 条
- `GET /mcp-registry/v0/servers...`：4 条

状态码分布：`200` 共 73 条；`HEAD /` 返回 `404` 共 1 条。

## Version Profile

- CLI UA：`claude-cli/2.1.187 (external, cli)`
- Code UA：`claude-code/2.1.187`
- GrowthBook eval / `HEAD /` UA：`Bun/1.4.0`
- `api/claude_code_penguin_mode` 与 `v1/mcp_servers` UA：`axios/1.15.2`
- `env.version=2.1.187`
- `env.version_base=2.1.187`
- `env.build_time=2026-06-23T16:59:46Z`
- `env.node_version=v24.3.0`
- `X-Stainless-Package-Version=0.94.0`
- `X-Stainless-Runtime=node`
- `X-Stainless-Runtime-Version=v24.3.0`

## `/v1/messages` Header / Body

- messages 总数：25 条；其中 24 条带 billing header。
- 模型分布：`claude-opus-4-8` 23 条；`claude-haiku-4-5-20251001` 2 条。
- `stream=true` 24 条；另有 1 条 Haiku `max_tokens=1` 探针非流式请求。
- `max_tokens` 分布：`64000` 23 条；`32000` 1 条；`1` 1 条。
- `thinking` 分布：`{"type":"adaptive"}` 23 条；`{"type":"disabled"}` 1 条；空 1 条。
- `metadata.user_id` 是 JSON 字符串，keys 为 `account_uuid`、`device_id`、`session_id`。
- Opus 主请求 body 顶层字段包含：`model`、`messages`、`system`、`tools`、`metadata`、`max_tokens`、`thinking`、`context_management`、`output_config`、`diagnostics`、`stream`。

Opus 主请求 beta 与 2.1.185 一致：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Haiku `max_tokens=1` 探针 beta：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05
```

Haiku 流式辅助请求 beta 新出现 `structured-outputs-2025-12-15`：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,advisor-tool-2026-03-01,structured-outputs-2025-12-15,cache-diagnosis-2026-04-07
```

该 beta 出现在真实客户端辅助请求中，不属于默认 Opus 主请求 `MESSAGE_BETA_TOKENS`；当前 cc2api 的 Claude Code 客户端模式会合并客户端传入 beta，因此本次不应把它硬编码进通用主画像。

## `cc_version`

- Haiku 流式辅助请求样本：`cc_version=2.1.187.cc1`
- Opus 主请求样本：`cc_version=2.1.187.338`
- 24 条带 billing 的 messages 中，24/24 命中既有后缀算法。
- 后缀算法仍为 `sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`，字符串索引按 JavaScript UTF-16 code unit 语义。
- 主请求首条 user message 仍可能有多个 text block，后缀文本源应取首条 user message 的最后一个 text block。

## CCH

24 条带 billing 的 messages 中，24/24 命中既有 `2.1.172+` CCH 归一化算法：

- seed：`0x4D659218E32A3268`
- 先将真实 `cch=<5hex>` 替回 `cch=00000`
- 顶层 `model` 值替换为 `""`
- 删除顶层 `max_tokens`
- 删除顶层 `fallbacks`
- `xxhash64(input, seed) & 0xFFFFF`

当前代码分支只把 `2.1.172`、`2.1.173`、`2.1.185` 纳入该归一化规则；实现 2.1.187 时必须把 `2.1.187` 显式加入同一分支，否则会退回 legacy seed/input 规则。

## Telemetry

- `POST /api/event_logging/v2/batch`：
  - UA：`claude-code/2.1.187`
  - beta：`oauth-2025-04-20`
  - `x-service-name=claude-code`
- payload 顶层 key：`events`
- 事件类型：
  - `ClaudeCodeInternalEvent`：689
  - `GrowthbookExperimentEvent`：3
- `event_data.email` 未出现。
- telemetry env 分布：
  - `version=2.1.187`
  - `version_base=2.1.187`
  - `build_time=2026-06-23T16:59:46Z`
  - `node_version=v24.3.0`
  - `shell=bash`
  - `is_running_with_bun=true`
  - `platform=linux`
- `additional_metadata` 是 base64 JSON；常见 key 包含 `subscription_type`、`renderer_mode`、`feature_name`、`queryChainId`、`requestId`、`model`、`provider`、`durationMs` 等。

Telemetry shape 与 2.1.185 的 `ClaudeCode2185` 结构一致，只需替换 identity 字段到 2.1.187。

## GrowthBook

- UA：`Bun/1.4.0`
- 请求顶层 key：`attributes`、`forcedFeatures`、`forcedVariations`、`url`
- `forcedFeatures` 类型为数组，`forcedVariations` 类型为对象，`url=""`
- attributes key：`accountUUID`、`appVersion`、`deviceID`、`entrypoint`、`firstTokenTime`、`id`、`organizationUUID`、`platform`、`rateLimitTier`、`sessionId`、`subscriptionType`、`userType`
- `appVersion=2.1.187`
- attributes 中没有 `email`

## Bootstrap

- 请求 UA：`claude-code/2.1.187`
- 请求 beta：`oauth-2025-04-20`
- response 顶层 key：`additional_model_costs`、`additional_model_options`、`auto_compact_windows`、`client_data`、`cwk_cfg_key`、`model_access`、`oauth_account`
- `client_data.cedar_lagoon` 包含 `claude-fable=true`、`claude-mythos=true`
- `client_data.cedar_basin=2026-08-31`
- `cwk_cfg_key=null`
- `additional_model_options` 包含 `claude-fable-5[1m]`，且 `disabled_reason` 显示 Fable 当前不可用。

Bootstrap response shape 与 2.1.185 任务记录一致；本次升级不需要修改 bootstrap 模型注入策略。

## Other Endpoint Headers

- `/api/oauth/account/settings`：UA `claude-cli/2.1.187 (external, cli)`，beta `oauth-2025-04-20`，无主动 JSON content-type。
- `/api/claude_code_grove`：UA `claude-cli/2.1.187 (external, cli)`，beta `oauth-2025-04-20`，无主动 JSON content-type。
- `/api/claude_code_penguin_mode`：UA `axios/1.15.2`，beta `oauth-2025-04-20`，无主动 JSON content-type。
- `/v1/code/triggers`：UA `claude-cli/2.1.187 (external, cli)`，beta `ccr-triggers-2026-01-30`，`anthropic-version=2023-06-01`，`anthropic-client-platform=claude_code_cli`。
- `/v1/mcp_servers?limit=1000`：UA `axios/1.15.2`，beta `mcp-servers-2025-12-04`，`anthropic-version=2023-06-01`，`mcp-protocol-version=2025-11-25`，`anthropic-mcp-client-capabilities` 与 2.1.185 相同。

## 与 2.1.185 对比结论

- identity 变化：`2.1.185` -> `2.1.187`，build_time 从 `2026-06-20T06:38:30Z` 变为 `2026-06-23T16:59:46Z`。
- Stainless SDK、Node runtime、GrowthBook UA、Telemetry shape、主请求 beta、`cc_version` 算法、CCH seed/input 规则均与 2.1.185 一致。
- 默认允许版本范围应升级为 `2.1.89-2.1.187`。
- 代码需要新增 `2.1.187` 内置 profile，并把默认 profile 切到 `2.1.187`，同时保留 `2.1.185` 和 `2.1.173` 可切回。
- 代码需要把 `2.1.187` 纳入 CCH 的 `2.1.172+` 分支。
- 启动迁移不能无条件把账号和 settings 写回默认 profile；否则管理员切到旧 profile 后重启，会出现 settings、账号 env、请求画像混用。
