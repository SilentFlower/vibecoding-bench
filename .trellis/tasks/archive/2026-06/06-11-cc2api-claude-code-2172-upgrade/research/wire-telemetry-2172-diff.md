# Claude Code 2.1.172 请求头、Bootstrap 与遥测差异记录

## 样本

- 169 baseline：`data/flows/pingguo-1/2873/10f2065adf44`
- 172 Opus：`data/flows/pingguo-1/3075/a773a0d683a6`
- 172 Fable：`data/flows/pingguo-1/3078/715232eae9e8`

本文只记录非敏感协议字段、字段名、版本号和 beta/profile 差异，不记录 token、Authorization、Cookie、账号邮箱、完整 prompt 或完整响应正文。

## `/v1/messages` 请求头

三组样本的 `/v1/messages?beta=true` header 名集合一致：

- `Accept`
- `Authorization`
- `Content-Type`
- `User-Agent`
- `X-Claude-Code-Session-Id`
- `X-Stainless-Arch`
- `X-Stainless-Lang`
- `X-Stainless-OS`
- `X-Stainless-Package-Version`
- `X-Stainless-Retry-Count`
- `X-Stainless-Runtime`
- `X-Stainless-Runtime-Version`
- `X-Stainless-Timeout`
- `anthropic-beta`
- `anthropic-dangerous-direct-browser-access`
- `anthropic-version`
- `x-app`
- `x-client-request-id`
- `Connection`
- `Host`
- `Accept-Encoding`
- `Content-Length`

主要版本差异：

- `User-Agent`：`claude-cli/2.1.169 (external, cli)` 升级为 `claude-cli/2.1.172 (external, cli)`。
- `X-Stainless-Package-Version`：保持 `0.94.0`。
- `X-Stainless-Runtime`：保持 `node`。
- `X-Stainless-Runtime-Version`：保持 `v24.3.0`。
- `X-Stainless-Timeout`：保持 `600`。
- `anthropic-version`：保持 `2023-06-01`。
- `x-app`：保持 `cli`。

结论：172 Fable 没有新增独立 header 名；需要处理的是 UA 版本、按模型 profile 生成的 `anthropic-beta`，以及请求体里的 `fallbacks`。

## `/v1/messages` Beta/Profile

Haiku/title 请求在 169、172 Opus、172 Fable 中保持同类画像，不包含 `claude-code-20250219` 和 `context-1m-2025-08-07`：

```text
oauth-2025-04-20,
interleaved-thinking-2025-05-14,
redact-thinking-2026-02-12,
thinking-token-count-2026-05-13,
context-management-2025-06-27,
prompt-caching-scope-2026-01-05
```

较完整的 Haiku/title 请求还会包含：

```text
advisor-tool-2026-03-01,
structured-outputs-2025-12-15,
cache-diagnosis-2026-04-07
```

169/172 Opus 主请求保持 Opus 1m profile，包含 `context-1m-2025-08-07`：

```text
claude-code-20250219,
oauth-2025-04-20,
context-1m-2025-08-07,
interleaved-thinking-2025-05-14,
redact-thinking-2026-02-12,
thinking-token-count-2026-05-13,
context-management-2025-06-27,
prompt-caching-scope-2026-01-05,
mid-conversation-system-2026-04-07,
advisor-tool-2026-03-01,
advanced-tool-use-2025-11-20,
effort-2025-11-24,
extended-cache-ttl-2025-04-11,
cache-diagnosis-2026-04-07
```

172 Fable 主请求不包含 `context-1m-2025-08-07`，包含 fallback 相关 beta：

```text
claude-code-20250219,
oauth-2025-04-20,
interleaved-thinking-2025-05-14,
redact-thinking-2026-02-12,
thinking-token-count-2026-05-13,
context-management-2025-06-27,
prompt-caching-scope-2026-01-05,
mid-conversation-system-2026-04-07,
advisor-tool-2026-03-01,
advanced-tool-use-2025-11-20,
effort-2025-11-24,
server-side-fallback-2026-06-01,
fallback-credit-2026-06-01,
extended-cache-ttl-2025-04-11,
cache-diagnosis-2026-04-07
```

Fable 主请求体：

- `model=claude-fable-5`
- `max_tokens=64000`
- `fallbacks=[{"model":"claude-opus-4-8"}]`
- `fallbacks` 实际发送，但不参与 172 Fable CCH hash 输入。

## Bootstrap

169 bootstrap：

- 请求路径：`/api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8`
- 请求 UA：`claude-code/2.1.169`
- `anthropic-beta=oauth-2025-04-20`
- response 中 `client_data=null`
- response 中 `additional_model_options=null`
- response 中 `cwk_cfg_key=null`

172 Opus bootstrap：

- 请求路径：`/api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8`
- 请求 UA：`claude-code/2.1.172`
- `anthropic-beta=oauth-2025-04-20`
- response 中 `client_data.cedar_lagoon={"claude-fable":true,"claude-mythos":true}`
- response 中 `additional_model_options` 包含 `model=claude-fable-5[1m]`、`name=Fable`
- response 中 `cwk_cfg_key=null`

172 Fable bootstrap：

- 请求路径：`/api/claude_cli/bootstrap?entrypoint=cli&model=claude-fable-5`
- 请求 UA：`claude-code/2.1.172`
- `anthropic-beta=oauth-2025-04-20`
- response 中 `client_data.cedar_lagoon={"claude-fable":true,"claude-mythos":true}`
- response 中 `additional_model_options` 包含 `model=claude-fable-5[1m]`、`name=Fable`
- response 中 `cwk_cfg_key="marigold"`

## 遥测 Metadata

Telemetry endpoint 为 `/api/event_logging/v2/batch`。

环境字段差异：

- 169：`env.version=2.1.169`、`env.version_base=2.1.169`、`env.build_time=2026-06-08T03:22:12Z`。
- 172：`env.version=2.1.172`、`env.version_base=2.1.172`、`env.build_time=2026-06-10T16:30:37Z`。
- 三组样本 `env.node_version=v24.3.0`。

169/172 Opus telemetry：

- 大多数 event model 为 `claude-opus-4-8[1m]`。
- `tengu_api_success` 中 event model 常见为 `claude-opus-4-8`，`additional_metadata.preNormalizedModel=claude-opus-4-8[1m]`。
- `tengu_cli_flags` 中 `flag_count=0`、`flags=""`。
- `tengu_startup_manual_model_config` 中 `settings_file=opus[1m]`、`settings_source=userSettings`。

172 Fable telemetry：

- 主请求相关 event model 为 `claude-fable-5`。
- `tengu_cli_flags` 中 `flag_count=1`、`flags=model`。
- `tengu_startup_manual_model_config` 中 `cli_flag=claude-fable-5`、`settings_file=opus[1m]`、`settings_source=userSettings`。
- `tengu_api_query` / `tengu_api_success` 的 `additional_metadata.model=claude-fable-5`，`betas` 与 Fable 主请求 beta 一致。
- Fable run 中仍有少量 `claude-opus-4-8[1m]` telemetry，来自启动和默认 settings 画像，不代表主 `/v1/messages` 使用 Opus。

`flags=model` 解释：

- 这是 CLI 启动参数画像信号，表示本次真实抓包通过 `--model` 一次性覆盖了 settings 中的 model。
- 它不是 Fable 上游 `/v1/messages` 协议字段，也不应作为 cc2api 通用 Fable 请求画像硬编码。
- 若 cc2api 后续要模拟 Claude Code telemetry，只有在确实存在一次性 model override 来源时才应生成 `flag_count=1`、`flags=model`、`cli_flag=<model>`；普通配置模型不应伪造该标记。

## `context-1m-2025-08-07` 策略

`context-1m-2025-08-07` 不应全局强塞到 2.1.172 所有请求。

- Opus `claude-opus-4-8[1m]` profile：继续包含 `context-1m-2025-08-07`。
- Fable `claude-fable-5` 主请求：不包含 `context-1m-2025-08-07`，改为包含 `server-side-fallback-2026-06-01` 与 `fallback-credit-2026-06-01`。
- Haiku/title 请求：保持自身 beta profile，不受主模型 1m/fallback profile 影响。

实现上应由模型/profile 决定 beta 列表，而不是按 Claude Code 版本统一注入 `context-1m-2025-08-07`。
