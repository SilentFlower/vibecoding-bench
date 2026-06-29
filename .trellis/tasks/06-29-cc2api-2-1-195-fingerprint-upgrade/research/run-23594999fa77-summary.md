# 抓包 23594999fa77 脱敏摘要

## 来源

- 远程目录：`/root/vibecoding-bench/data/flows/6-23/4638/23594999fa77/`
- 本地原始证据：`.trellis/tasks/06-29-cc2api-2-1-195-fingerprint-upgrade/evidence/run-23594999fa77/`
- 原始证据文件：`capture_index.json`、`stats.jsonl`、`http_capture.jsonl`、`20260629-030944.flow`
- 敏感边界：任务内 `.gitignore` 已排除 `evidence/`，不得提交完整请求/响应正文、token、Cookie、邮箱、账号 UUID 或完整 prompt。

## 流量概览

- flow 总数：86
- `/v1/messages`：31 条，其中 30 条包含 `x-anthropic-billing-header` 注入文本。
- `/api/event_logging/v2/batch`：43 批，包含 829 个事件。
- bootstrap：1 条 `/api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8`。
- 其它关键端点：`/api/eval/sdk-zAZezfDKGoZuXXKe`、`/api/claude_code_grove`、`/api/claude_code_penguin_mode`、`/api/oauth/account/settings`、`/mcp-registry/v0/servers`、`/v1/code/triggers`、`/v1/mcp_servers`。

## 2.1.195 请求画像

### `/v1/messages`

- `User-Agent`：`claude-cli/2.1.195 (external, cli)`。
- `x-app`：`cli`。
- `anthropic-version`：`2023-06-01`。
- `X-Stainless-Package-Version`：`0.94.0`。
- `X-Stainless-Runtime`：`node`。
- `X-Stainless-Runtime-Version`：`v26.3.0`。
- `X-Stainless-Timeout`：`600`。
- `X-Stainless-Retry-Count`：`0`。
- 模型分布：`claude-haiku-4-5-20251001` 2 条，`claude-opus-4-8` 29 条。
- Haiku 非流探测 beta：
  `oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05`
- Haiku 流式标题 beta：
  `oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,advisor-tool-2026-03-01,structured-outputs-2025-12-15,cache-diagnosis-2026-04-07`
- Opus `[1m]` 主请求 beta：
  `claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07`

### billing / CCH

- `cc_version` 后缀复算：30/30 命中现有 `sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version)[0:3]` 算法。
- Haiku 流式标题请求：`cc_version=2.1.195.113`。
- Opus 主请求：`cc_version=2.1.195.aff`。
- CCH 复算：30/30 命中 `2.1.172+` 规则：
  - seed：`0x4D659218E32A3268`
  - 输入规范化：真实 `cch=<5hex>` 替换回 `cch=00000`，top-level `model` 置空，删除 top-level `max_tokens` 和 `fallbacks`。
- 完整 body 规则、legacy seed、legacy+规范化均 0/30 命中。

### endpoint / UA 差异

- `/api/claude_cli/bootstrap`：`User-Agent=claude-code/2.1.195`，`anthropic-beta=oauth-2025-04-20`。
- `/api/event_logging/v2/batch`：`User-Agent=claude-code/2.1.195`，`anthropic-beta=oauth-2025-04-20`。
- `/api/eval/*`：`User-Agent=Bun/1.4.0`，`anthropic-beta=oauth-2025-04-20`。
- `/api/claude_code_penguin_mode`：`User-Agent=axios/1.15.2`，`anthropic-beta=oauth-2025-04-20`。
- `/v1/mcp_servers`：`User-Agent=axios/1.15.2`，`anthropic-beta=mcp-servers-2025-12-04`，`mcp-protocol-version=2025-11-25`，`anthropic-mcp-client-capabilities=eyJyb290cyI6e30sImVsaWNpdGF0aW9uIjp7fX0=`。
- `/v1/code/triggers`：`User-Agent=claude-cli/2.1.195 (external, cli)`，`anthropic-beta=ccr-triggers-2026-01-30`，`anthropic-client-platform=claude_code_cli`。

## telemetry 画像

- `env.version`：`2.1.195`
- `env.version_base`：`2.1.195`
- `env.build_time`：`2026-06-26T01:00:56Z`
- `env.node_version`：`v26.3.0`
- `env.platform`：`linux`
- `env.arch`：`x64`
- `env.terminal`：`tmux`
- `env.shell`：`bash`
- `env.deployment_environment`：`docker`
- `env.linux_distro_id`：`debian`
- `env.linux_distro_version`：`12`
- 事件结构仍是 `events[].event_type + events[].event_data`，与现有 `ClaudeCode2185` shape 兼容。
- 主要事件名包括 `tengu_feature_ok`、`tengu_api_cache_breakpoints`、`tengu_sysprompt_boundary_found`、`tengu_api_before_normalize`、`tengu_api_after_normalize`、`tengu_api_query`、`tengu_api_success`、`tengu_api_slow_first_byte` 等。

## bootstrap 摘要

- response 顶层 key：
  `additional_model_costs`、`additional_model_options`、`auto_compact_windows`、`client_data`、`cwk_cfg_key`、`model_access`、`oauth_account`、`org_model_default`
- `client_data` 包含 `cedar_basin`、`cedar_lagoon`。
- `additional_model_options` 有 1 项，结构包含 `model`、`name`、`description`、`disabled_reason`。
- `cwk_cfg_key` 为 `null`。

## 对当前 cc2api 的初步差异

- 必改：默认 profile 从 `2.1.187` 升到 `2.1.195`。
- 必改：`DEFAULT_CLAUDE_CODE_BUILD_TIME` 对齐 `2026-06-26T01:00:56Z`。
- 必改：Stainless / Node runtime 版本从 `v24.3.0` 升到 `v26.3.0`，影响 `X-Stainless-Runtime-Version`、OAuth token test、identity env、telemetry env。
- 必改：`allowed_claude_code_versions` 上限从 `2.1.187` 扩到 `2.1.195`。
- 可复用：`STAINLESS_PACKAGE_VERSION=0.94.0` 不变。
- 可复用：message beta、Haiku beta、MCP capabilities、MCP protocol、code triggers beta、event logging path 未发现变化。
- 可复用：`cc_version` 后缀算法未变。
- 可复用：CCH seed 与 2.1.172+ top-level 规范化规则未变，但代码白名单需要包含 `2.1.195`。
