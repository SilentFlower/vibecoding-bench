# Claude Code 2.1.156 抓包结构化分析

## 样本

- run: `46ba25a8d791`
- 文件: `data/flows/auto-2/1887/46ba25a8d791/http_capture.jsonl`
- 脱敏策略: 只记录端点、header key、body 顶层字段、事件名、版本字段和 body SHA256 前缀；不记录 token、prompt、请求体全文或响应体全文。

## 端点与响应状态

| method | path | count | status |
|---|---|---:|---|
| `HEAD` | `/` | 1 | `404:1` |
| `GET` | `/api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8` | 1 | `200:1` |
| `GET` | `/api/claude_code_grove` | 1 | `200:1` |
| `GET` | `/api/claude_code_penguin_mode` | 1 | `200:1` |
| `POST` | `/api/eval/sdk-zAZezfDKGoZuXXKe` | 1 | `200:1` |
| `POST` | `/api/event_logging/v2/batch` | 31 | `200:31` |
| `GET` | `/api/oauth/account/settings` | 1 | `200:1` |
| `GET` | `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth` | 1 | `200:1` |
| `GET` | `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth&cursor=com.box.mcp%2Fbox%3A1.0.0` | 1 | `200:1` |
| `GET` | `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth&cursor=com.mercury.mcp%2Fmercury%3A1.0.0` | 1 | `200:1` |
| `GET` | `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth&cursor=io.eraser%2Feraser%3A1.0.0` | 1 | `200:1` |
| `GET` | `/v1/code/triggers` | 1 | `200:1` |
| `GET` | `/v1/mcp_servers?limit=1000` | 1 | `200:1` |
| `POST` | `/v1/messages?beta=true` | 17 | `200:17` |

## Header Key 分布

| path | header keys |
|---|---|
| `/` | `Accept, Accept-Encoding, Connection, Host, User-Agent` |
| `/api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8` | `Accept, Accept-Encoding, anthropic-beta, Authorization, Connection, Content-Type, Host, User-Agent` |
| `/api/claude_code_grove` | `Accept, Accept-Encoding, anthropic-beta, Authorization, Connection, Host, User-Agent` |
| `/api/claude_code_penguin_mode` | `Accept, Accept-Encoding, anthropic-beta, Authorization, Connection, Host, User-Agent` |
| `/api/eval/sdk-zAZezfDKGoZuXXKe` | `Accept, Accept-Encoding, anthropic-beta, Authorization, Connection, Content-Length, Content-Type, Host, User-Agent` |
| `/api/event_logging/v2/batch` | `Accept, Accept-Encoding, anthropic-beta, Authorization, Connection, Content-Length, Content-Type, Host, User-Agent, x-service-name` |
| `/api/oauth/account/settings` | `Accept, Accept-Encoding, anthropic-beta, Authorization, Connection, Host, User-Agent` |
| `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth` | `Accept, Accept-Encoding, Connection, Host, User-Agent` |
| `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth&cursor=com.box.mcp%2Fbox%3A1.0.0` | `Accept, Accept-Encoding, Connection, Host, User-Agent` |
| `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth&cursor=com.mercury.mcp%2Fmercury%3A1.0.0` | `Accept, Accept-Encoding, Connection, Host, User-Agent` |
| `/mcp-registry/v0/servers?version=latest&limit=100&visibility=commercial%2Cgsuite%2Centerprise%2Chealth&cursor=io.eraser%2Feraser%3A1.0.0` | `Accept, Accept-Encoding, Connection, Host, User-Agent` |
| `/v1/code/triggers` | `Accept, Accept-Encoding, anthropic-beta, anthropic-client-platform, anthropic-version, Authorization, Connection, Content-Type, Host, User-Agent, x-organization-uuid` |
| `/v1/mcp_servers?limit=1000` | `Accept, Accept-Encoding, anthropic-beta, anthropic-version, Authorization, Connection, Content-Type, Host, User-Agent` |
| `/v1/messages?beta=true` | `Accept, Accept-Encoding, anthropic-beta, anthropic-dangerous-direct-browser-access, anthropic-version, Authorization, Connection, Content-Length, Content-Type, Host, User-Agent, x-app, X-Claude-Code-Session-Id, x-client-request-id, X-Stainless-Arch, X-Stainless-Lang, X-Stainless-OS, X-Stainless-Package-Version, X-Stainless-Retry-Count, X-Stainless-Runtime, X-Stainless-Runtime-Version, X-Stainless-Timeout` |

## Body 顶层字段

| path | fields |
|---|---|
| `/api/eval/sdk-zAZezfDKGoZuXXKe` | `attributes, forcedFeatures, forcedVariations, url` |
| `/api/event_logging/v2/batch` | `events` |
| `/v1/messages?beta=true` | `context_management, diagnostics, max_tokens, messages, metadata, model, output_config, stream, system, temperature, thinking, tools` |

## /v1/messages 模型分布

- `claude-haiku-4-5-20251001`: 2
- `claude-opus-4-8`: 15

## Event Logging 事件名

- `GrowthbookExperimentEvent`: 4
- `tengu_ant_overly_broad_bash_detected`: 1
- `tengu_api_after_normalize`: 16
- `tengu_api_before_normalize`: 16
- `tengu_api_cache_breakpoints`: 32
- `tengu_api_query`: 16
- `tengu_api_slow_first_byte`: 9
- `tengu_api_success`: 16
- `tengu_attachment_compute_duration`: 23
- `tengu_attachments`: 3
- `tengu_auto_updater_fail`: 1
- `tengu_auto_updater_npm_failure`: 1
- `tengu_bash_ast_too_complex`: 1
- `tengu_bash_tool_command_executed`: 4
- `tengu_claudeai_limits_status_changed`: 1
- `tengu_claudeai_mcp_eligibility`: 1
- `tengu_claudemd__initial_load`: 1
- `tengu_cli_flags`: 1
- `tengu_context_size`: 1
- `tengu_deferred_tools_pool_change`: 1
- `tengu_dir_search`: 6
- `tengu_edit_string_lengths`: 1
- `tengu_exit`: 1
- `tengu_feature_bad`: 1
- `tengu_feature_ok`: 119
- `tengu_file_changed`: 9
- `tengu_file_history_snapshot_success`: 1
- `tengu_file_history_track_edit_success`: 8
- `tengu_file_operation`: 9
- `tengu_file_suggestions_ripgrep`: 1
- `tengu_fork_agent_query`: 1
- `tengu_init`: 1
- `tengu_input_prompt`: 1
- `tengu_mcp_registry_fetch`: 1
- `tengu_mcp_servers`: 1
- `tengu_memdir_disabled`: 1
- `tengu_paste_text`: 1
- `tengu_plugins_loaded`: 1
- `tengu_policy_limits_cache_state_at_first_prompt`: 1
- `tengu_prompt_suggestion_init`: 2
- `tengu_query_after_attachments`: 13
- `tengu_query_before_attachments`: 13
- `tengu_render_glyph_cardinality`: 1
- `tengu_repl_hook_finished`: 10
- `tengu_ripgrep_availability`: 1
- `tengu_run_hook`: 1
- `tengu_session_title_generated`: 1
- `tengu_shell_set_cwd`: 1
- `tengu_skill_loaded`: 14
- `tengu_spinner_stall_cleared`: 12
- `tengu_spinner_stalled_ui`: 17
- `tengu_started`: 1
- `tengu_startup_manual_model_config`: 1
- `tengu_startup_telemetry`: 1
- `tengu_sysprompt_block`: 16
- `tengu_sysprompt_boundary_found`: 30
- `tengu_sysprompt_missing_boundary_marker`: 2
- `tengu_terminal_probe`: 1
- `tengu_timer`: 2
- `tengu_tip_shown`: 1
- `tengu_tool_search_mode_decision`: 16
- `tengu_tool_use_can_use_tool_allowed`: 13
- `tengu_tool_use_granted_in_config`: 13
- `tengu_tool_use_success`: 13

## Billing 样本摘要

| path | cc_version | cch | body_sha256_12 |
|---|---|---|---|
| `/v1/messages?beta=true` | `2.1.156.b2a` | `36de0` | `416442fe224a` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `47eae` | `43a0c60db48d` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `9df1f` | `3f5ce03fc60c` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `7ad44` | `e1494a02deb9` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `d49be` | `08d37c5f95d1` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `5c808` | `4897f47d5800` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `945c8` | `05e543af2807` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `ab56e` | `e2683bd75ec6` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `766d0` | `7d713aa4643d` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `e7823` | `aab0dd7830fb` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `c8241` | `4ace5405c15a` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `3b62a` | `c027a9f58f60` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `776c3` | `954e6c4e19db` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `da5cd` | `440a7ebad562` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `f69e0` | `459dd8fd9792` |
| `/v1/messages?beta=true` | `2.1.156.b94` | `1c720` | `a2b0bc625400` |

## 结论

- `/api/event_logging/v2/batch` 是本次抓包的主要遥测批量端点，旧 `/api/event_logging/batch` 未出现。
- `/v1/messages` 使用 `claude-cli/2.1.156 (external, cli)`、`X-Stainless-Package-Version=0.94.0`、`X-Stainless-Runtime-Version=v24.3.0`。
- `/api/event_logging/v2/batch` 使用 `claude-code/2.1.156` 和 `x-service-name=claude-code`。
- `/api/eval/*` 抓包 UA 为 `Bun/1.3.14`，实现上优先按 endpoint profile 保守模拟。
- billing 行中 `cc_version` 后缀和 5 位 `cch` 存在；CCH 已在第一轮研究中证明不能用旧最终 body xxhash 算法复现。
