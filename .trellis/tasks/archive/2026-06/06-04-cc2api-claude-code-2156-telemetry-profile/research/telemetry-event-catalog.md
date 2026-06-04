# Claude Code 2.1.156 遥测事件安全目录

## 输入边界

来源为 `data/flows/auto-2/1887/46ba25a8d791/http_capture.jsonl` 的结构化解析结果。本目录只记录 endpoint、事件名、字段路径、字段类型、出现次数、batch 大小和时间间隔摘要；不记录 token、prompt、请求体全文、响应体全文、账号真实 profile 或 `.flow` 原文。

## Endpoint 摘要

| endpoint | flow 数 | status | 事件总数 |
|---|---:|---|---:|
| `/api/event_logging/v2/batch` | 31 | 200 | 510 |

事件类型分布：

| event_type | 数量 |
|---|---:|
| `ClaudeCodeInternalEvent` | 506 |
| `GrowthbookExperimentEvent` | 4 |

Batch 摘要：

| 指标 | 值 |
|---|---:|
| batch size min | 1 |
| batch size median | 10 |
| batch size max | 88 |
| 相邻 batch 间隔 min | 10.156s |
| 相邻 batch 间隔 median | 14.940s |
| 相邻 batch 间隔 max | 58.891s |

## 高频事件名

| event_name | 数量 |
|---|---:|
| `tengu_feature_ok` | 119 |
| `tengu_api_cache_breakpoints` | 32 |
| `tengu_sysprompt_boundary_found` | 30 |
| `tengu_attachment_compute_duration` | 23 |
| `tengu_spinner_stalled_ui` | 17 |
| `tengu_tool_search_mode_decision` | 16 |
| `tengu_api_before_normalize` | 16 |
| `tengu_api_after_normalize` | 16 |
| `tengu_sysprompt_block` | 16 |
| `tengu_api_query` | 16 |
| `tengu_api_success` | 16 |
| `tengu_skill_loaded` | 14 |
| `tengu_tool_use_granted_in_config` | 13 |
| `tengu_tool_use_can_use_tool_allowed` | 13 |
| `tengu_tool_use_success` | 13 |
| `tengu_query_before_attachments` | 13 |
| `tengu_query_after_attachments` | 13 |
| `tengu_spinner_stall_cleared` | 12 |
| `tengu_repl_hook_finished` | 10 |
| `tengu_api_slow_first_byte` | 9 |
| `tengu_file_changed` | 9 |
| `tengu_file_operation` | 9 |
| `tengu_file_history_track_edit_success` | 8 |
| `tengu_dir_search` | 6 |
| `GrowthbookExperimentEvent` 无 `event_name` | 4 |
| `tengu_bash_tool_command_executed` | 4 |

## 共同字段形态

高频 `ClaudeCodeInternalEvent` 的 `event_data` 共同字段：

| 字段路径 | 类型 |
|---|---|
| `event_name` | string |
| `client_timestamp` | string |
| `model` | string |
| `session_id` | string |
| `user_type` | string |
| `betas` | string |
| `env` | object |
| `env.platform` | string |
| `env.node_version` | string |
| `env.terminal` | string |
| `env.package_managers` | string |
| `env.runtimes` | string |
| `env.is_running_with_bun` | bool |
| `env.is_ci` | bool |
| `env.is_claubbit` | bool |
| `env.is_github_action` | bool |
| `env.is_claude_code_action` | bool |
| `env.is_claude_ai_auth` | bool |
| `env.version` | string |
| `env.arch` | string |
| `env.is_claude_code_remote` | bool |
| `env.deployment_environment` | string |
| `env.is_conductor` | bool |
| `env.version_base` | string |
| `env.build_time` | string |
| `env.is_local_agent_mode` | bool |
| `env.linux_distro_id` | string |
| `env.linux_distro_version` | string |
| `env.linux_kernel` | string |
| `env.platform_raw` | string |
| `env.shell` | string |
| `entrypoint` | string |
| `is_interactive` | bool |
| `client_type` | string |
| `process` | string |
| `additional_metadata` | string |
| `auth` | object |
| `auth.organization_uuid` | string |
| `auth.account_uuid` | string |
| `event_id` | string |
| `device_id` | string |
| `email` | string |

少量事件有专用安全字段，例如 `tengu_skill_loaded` 带 `skill_name:string`。首轮 cc2api 模板只使用安全派生字段，不写入 prompt、tool input、响应体或 token。

## 首轮实现决策

- 自动遥测改为事件队列，batch 由队列驱动，空队列不再固定伪造 `tengu_api_success`。
- `/v1/messages` 成功链路生成 `tengu_api_before_normalize`、`tengu_api_after_normalize`、`tengu_sysprompt_boundary_found`、`tengu_sysprompt_block`、`tengu_api_query`、`tengu_api_success`。
- 上游首字节超过阈值时追加 `tengu_api_slow_first_byte`。
- 启动低频事件生成 `tengu_started`、`tengu_init`、`tengu_startup_telemetry`、`tengu_feature_ok`。
- 工具/技能/附件类首轮只生成安全占位事件，不从请求体提取工具输入原文。
- 继续拦截真实客户端 telemetry 请求；真实 telemetry body 的身份字段改写逻辑保留在 `rewriter.rs`，默认不透传原文到上游。
