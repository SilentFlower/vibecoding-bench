# Claude Code 2.1.195 telemetry 脱敏事件目录

## 输入边界

- 来源：`23594999fa77` 本地 evidence 的 `http_capture.jsonl`。
- 本目录只记录 endpoint、事件名、字段名、字段类型、出现次数、来源和敏感等级。
- 不记录 token、Cookie、Authorization、邮箱、完整账号 UUID、prompt、tool input、响应正文或原始抓包 body。

## Batch 摘要

| 指标 | 值 |
|---|---:|
| batch 数 | 43 |
| 事件总数 | 829 |
| batch size min/median/max | 1 / 20 / 92 |
| batch 间隔 min/median/max | 0.479s / 14.975s / 33.168s |

## 与历史版本的脱敏对比

- 2.1.195 仍沿用 2.1.185 / 2.1.187 的 `ClaudeCode2185` telemetry shape：`event_data.email` 不出现，`additional_metadata` 是 base64 JSON，GrowthBook payload 使用 `forcedVariations` / 数组 `forcedFeatures` / `url`。
- 2.1.187 既有脱敏摘要记录 `ClaudeCodeInternalEvent=689`、`GrowthbookExperimentEvent=3`，常见 metadata key 包含 `subscription_type`、`renderer_mode`、`feature_name`、`queryChainId`、`requestId`、`model`、`provider`、`durationMs`。
- 2.1.185 既有脱敏摘要记录 `ClaudeCodeInternalEvent=462`、`GrowthbookExperimentEvent=5`，且 `preNormalizedModel` / `flags` 未出现有效值。
- 2.1.195 的主要变化不是 shape 换代，而是事件量、metadata 密度和版本身份字段；本轮实现按 `ClaudeCode2185` shape 保留顶层 `event_data`，把新增请求链、usage、cache、tool、附件字段写入 `additional_metadata`。
- 本对比只引用历史任务中的脱敏摘要，不提交 2.1.187 / 2.1.185 原始抓包。

## 事件名分布

| event_name | 数量 |
|---|---:|
| `tengu_feature_ok` | 158 |
| `tengu_api_cache_breakpoints` | 60 |
| `tengu_sysprompt_boundary_found` | 58 |
| `tengu_attachment_compute_duration` | 48 |
| `tengu_tool_search_mode_decision` | 30 |
| `tengu_api_before_normalize` | 30 |
| `tengu_api_after_normalize` | 30 |
| `tengu_sysprompt_block` | 30 |
| `tengu_api_query` | 30 |
| `tengu_api_success` | 30 |
| `tengu_tool_use_granted_in_config` | 28 |
| `tengu_tool_use_can_use_tool_allowed` | 28 |
| `tengu_query_before_attachments` | 28 |
| `tengu_query_after_attachments` | 28 |
| `tengu_tool_use_success` | 24 |
| `tengu_spinner_stalled_ui` | 17 |
| `tengu_skill_loaded` | 15 |
| `tengu_bash_tool_command_executed` | 13 |
| `tengu_spinner_stall_cleared` | 12 |
| `tengu_repl_hook_finished` | 12 |
| `tengu_file_changed` | 11 |
| `tengu_file_operation` | 11 |
| `tengu_file_history_track_edit_success` | 9 |
| `tengu_api_slow_first_byte` | 8 |
| `tengu_dir_search` | 6 |
| `tengu_bash_ast_too_complex` | 6 |
| `tengu_shell_set_cwd` | 5 |
| `tengu_attachments` | 5 |
| `tengu_bash_tool_command_failed` | 4 |
| `tengu_feature_sad` | 4 |
| `tengu_tool_use_error` | 4 |
| `tengu_plugin_name_collision` | 2 |
| `tengu_timer` | 2 |
| `tengu_prompt_suggestion_init` | 2 |
| `GrowthbookExperimentEvent` | 2 |
| `tengu_sysprompt_missing_boundary_marker` | 2 |
| `tengu_edit_string_lengths` | 2 |
| `tengu_cli_flags` | 1 |
| `tengu_ant_overly_broad_bash_detected` | 1 |
| `tengu_started` | 1 |
| `tengu_exit` | 1 |
| `tengu_plugin_skills_dir_loaded` | 1 |
| `tengu_claudemd__initial_load` | 1 |
| `tengu_init` | 1 |
| `tengu_shell_allow_rules_at_init` | 1 |
| `tengu_startup_manual_model_config` | 1 |
| `tengu_voice_init_gate` | 1 |
| `tengu_bridge_repl_evaluated` | 1 |
| `tengu_plugins_loaded` | 1 |
| `tengu_startup_telemetry` | 1 |
| `tengu_ripgrep_availability` | 1 |
| `tengu_fork_subagent_enabled` | 1 |
| `tengu_context_size` | 1 |
| `tengu_file_suggestions_ripgrep` | 1 |
| `tengu_client_data_cache_key` | 1 |
| `tengu_claudeai_mcp_eligibility` | 1 |
| `tengu_mcp_servers` | 1 |
| `tengu_terminal_probe` | 1 |
| `tengu_claudeai_limits_status_changed` | 1 |
| `tengu_mcp_registry_fetch` | 1 |
| `tengu_render_glyph_cardinality` | 1 |
| `tengu_paste_text` | 1 |
| `tengu_deferred_tools_pool_change` | 1 |
| `tengu_input_prompt` | 1 |
| `tengu_file_history_snapshot_success` | 1 |
| `tengu_policy_limits_cache_state_at_first_prompt` | 1 |
| `tengu_memdir_disabled` | 1 |
| `tengu_session_title_generated` | 1 |
| `tengu_prompt_suggestion` | 1 |
| `tengu_run_hook` | 1 |
| `tengu_tip_shown` | 1 |
| `tengu_config_cache_stats` | 1 |

## 重点事件 additional_metadata

### `tengu_api_before_normalize`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `subscription_type` | 30/30 | string:30 | 账号 profile 可推导 | 低 |
| `preNormalizedMessageCount` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |

### `tengu_api_after_normalize`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `subscription_type` | 30/30 | string:30 | 账号 profile 可推导 | 低 |
| `postNormalizedMessageCount` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |

### `tengu_api_query`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `subscription_type` | 30/30 | string:30 | 账号 profile 可推导 | 低 |
| `model` | 30/30 | string:30 | 请求体可推导 | 低 |
| `messagesLength` | 30/30 | int:30 | 请求体可推导 | 低 |
| `temperature` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `provider` | 30/30 | string:30 | 网关运行时可推导 | 低 |
| `buildAgeMins` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `betas` | 30/30 | string:30 | 请求 header 可推导 | 低 |
| `permissionMode` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `querySource` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `thinkingType` | 30/30 | string:30 | 请求体可推导 | 低 |
| `fastMode` | 30/30 | bool:30 | 待分级或客户端本地不可得 | 中 |
| `queryChainId` | 29/30 | string:29 | 网关运行时可推导 | 低 |
| `queryDepth` | 29/30 | int:29 | 网关运行时可推导 | 低 |
| `effortValue` | 29/30 | string:29 | 待分级或客户端本地不可得 | 中 |
| `previousRequestId` | 28/30 | string:28 | 网关运行时可推导 | 低 |

### `tengu_api_success`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `subscription_type` | 30/30 | string:30 | 账号 profile 可推导 | 低 |
| `model` | 30/30 | string:30 | 请求体可推导 | 低 |
| `betas` | 30/30 | string:30 | 请求 header 可推导 | 低 |
| `messageCount` | 30/30 | int:30 | 请求体可推导 | 低 |
| `messageTokens` | 30/30 | int:30 | 响应 usage 可推导 | 低 |
| `inputTokens` | 30/30 | int:30 | 响应 usage 可推导 | 低 |
| `outputTokens` | 30/30 | int:30 | 响应 usage 可推导 | 低 |
| `cachedInputTokens` | 30/30 | int:30 | 响应 usage 可推导 | 低 |
| `uncachedInputTokens` | 30/30 | int:30 | 响应 usage 可推导 | 低 |
| `durationMs` | 30/30 | int:30 | 响应可推导 | 低 |
| `durationMsIncludingRetries` | 30/30 | int:30 | 响应可推导 | 低 |
| `attempt` | 30/30 | int:30 | 网关运行时可推导 | 低 |
| `ttftMs` | 30/30 | int:30 | 响应可推导 | 低 |
| `buildAgeMins` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `provider` | 30/30 | string:30 | 网关运行时可推导 | 低 |
| `requestId` | 30/30 | string:30 | 网关运行时可推导 | 低 |
| `stop_reason` | 30/30 | string:30 | 响应可推导 | 低 |
| `costUSD` | 30/30 | float:30 | 待分级或客户端本地不可得 | 中 |
| `didFallBackToNonStreaming` | 30/30 | bool:30 | 待分级或客户端本地不可得 | 中 |
| `isNonInteractiveSession` | 30/30 | bool:30 | 待分级或客户端本地不可得 | 中 |
| `print` | 30/30 | bool:30 | 待分级或客户端本地不可得 | 中 |
| `isTTY` | 30/30 | bool:30 | 待分级或客户端本地不可得 | 中 |
| `querySource` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `permissionMode` | 30/30 | string:30 | 客户端本地不可得 | 低 |
| `globalCacheStrategy` | 30/30 | string:30 | 待分级或客户端本地不可得 | 中 |
| `textContentLength` | 30/30 | int:30 | 请求体可推导但需避免正文 | 中 |
| `imageBlockCount` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `imageTotalPixels` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `imageTotalBytes` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `documentBlockCount` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `documentTotalBytes` | 30/30 | int:30 | 待分级或客户端本地不可得 | 中 |
| `inputTextCharLength` | 30/30 | int:30 | 请求体可推导但需避免正文 | 中 |
| `estimatedInputTokens` | 30/30 | int:30 | 请求体可推导但需避免正文 | 中 |
| `fastMode` | 30/30 | bool:30 | 待分级或客户端本地不可得 | 中 |
| `preNormalizedModel` | 29/30 | string:29 | 请求体可推导 | 低 |
| `queryChainId` | 29/30 | string:29 | 网关运行时可推导 | 低 |
| `queryDepth` | 29/30 | int:29 | 网关运行时可推导 | 低 |
| `timeSinceLastApiCallMs` | 29/30 | int:29 | 待分级或客户端本地不可得 | 中 |
| `toolUseContentLengths` | 28/30 | string:28 | 待分级或客户端本地不可得 | 中 |
| `previousRequestId` | 28/30 | string:28 | 网关运行时可推导 | 低 |
| `thinkingContentLength` | 25/30 | int:25 | 待分级或客户端本地不可得 | 中 |

### `tengu_api_cache_breakpoints`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 60/60 | string:60 | 客户端本地不可得 | 低 |
| `subscription_type` | 60/60 | string:60 | 账号 profile 可推导 | 低 |
| `totalMessageCount` | 60/60 | int:60 | 请求体可推导 | 低 |
| `cachingEnabled` | 60/60 | bool:60 | 待分级或客户端本地不可得 | 中 |
| `skipCacheWrite` | 60/60 | bool:60 | 待分级或客户端本地不可得 | 中 |
| `forkPointPinned` | 60/60 | bool:60 | 待分级或客户端本地不可得 | 中 |
| `markerCount` | 60/60 | int:60 | 请求体可推导 | 低 |

### `tengu_sysprompt_boundary_found`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 58/58 | string:58 | 客户端本地不可得 | 低 |
| `subscription_type` | 58/58 | string:58 | 账号 profile 可推导 | 低 |
| `blockCount` | 58/58 | int:58 | 请求体可推导 | 低 |
| `staticBlockLength` | 58/58 | int:58 | 请求体可推导但需避免正文 | 中 |
| `dynamicBlockLength` | 58/58 | int:58 | 请求体可推导但需避免正文 | 中 |

### `tengu_tool_use_can_use_tool_allowed`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 28/28 | string:28 | 客户端本地不可得 | 低 |
| `subscription_type` | 28/28 | string:28 | 账号 profile 可推导 | 低 |
| `messageID` | 28/28 | string:28 | 网关运行时可推导 | 低 |
| `toolName` | 28/28 | string:28 | 请求工具 schema 可推导 | 低 |
| `queryChainId` | 28/28 | string:28 | 网关运行时可推导 | 低 |
| `queryDepth` | 28/28 | int:28 | 网关运行时可推导 | 低 |
| `requestId` | 28/28 | string:28 | 网关运行时可推导 | 低 |

### `tengu_tool_use_success`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 24/24 | string:24 | 客户端本地不可得 | 低 |
| `subscription_type` | 24/24 | string:24 | 账号 profile 可推导 | 低 |
| `messageID` | 24/24 | string:24 | 网关运行时可推导 | 低 |
| `toolName` | 24/24 | string:24 | 请求工具 schema 可推导 | 低 |
| `isMcp` | 24/24 | bool:24 | 待分级或客户端本地不可得 | 中 |
| `durationMs` | 24/24 | int:24 | 响应可推导 | 低 |
| `rssDeltaBytes` | 24/24 | int:24 | 待分级或客户端本地不可得 | 中 |
| `heapUsedDeltaBytes` | 24/24 | int:24 | 待分级或客户端本地不可得 | 中 |
| `externalDeltaBytes` | 24/24 | int:24 | 待分级或客户端本地不可得 | 中 |
| `preToolHookDurationMs` | 24/24 | int:24 | 待分级或客户端本地不可得 | 中 |
| `permissionDurationMs` | 24/24 | int:24 | 待分级或客户端本地不可得 | 中 |
| `toolResultSizeBytes` | 24/24 | int:24 | 响应可推导但需避免正文 | 中 |
| `toolInputSizeBytes` | 24/24 | int:24 | 请求体可推导但需避免正文 | 中 |
| `queryChainId` | 24/24 | string:24 | 网关运行时可推导 | 低 |
| `queryDepth` | 24/24 | int:24 | 网关运行时可推导 | 低 |
| `requestId` | 24/24 | string:24 | 网关运行时可推导 | 低 |
| `fileExtension` | 15/24 | string:15 | 待分级或客户端本地不可得 | 中 |
| `bashCommandLen` | 13/24 | int:13 | 待分级或客户端本地不可得 | 中 |
| `filePathLen` | 11/24 | int:11 | 待分级或客户端本地不可得 | 中 |
| `bashCommandFileExtensions` | 1/24 | string:1 | 待分级或客户端本地不可得 | 中 |

### `tengu_attachment_compute_duration`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 48/48 | string:48 | 客户端本地不可得 | 低 |
| `subscription_type` | 48/48 | string:48 | 账号 profile 可推导 | 低 |
| `label` | 48/48 | string:48 | 待分级或客户端本地不可得 | 中 |
| `duration_ms` | 48/48 | int:48 | 待分级或客户端本地不可得 | 中 |
| `attachment_size_bytes` | 48/48 | int:48 | 待分级或客户端本地不可得 | 中 |
| `attachment_count` | 48/48 | int:48 | 待分级或客户端本地不可得 | 中 |

### `tengu_file_operation`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 11/11 | string:11 | 客户端本地不可得 | 低 |
| `subscription_type` | 11/11 | string:11 | 账号 profile 可推导 | 低 |
| `operation` | 11/11 | string:11 | 待分级或客户端本地不可得 | 中 |
| `tool` | 11/11 | string:11 | 待分级或客户端本地不可得 | 中 |
| `filePathHash` | 11/11 | string:11 | 待分级或客户端本地不可得 | 中 |
| `type` | 9/11 | string:9 | 待分级或客户端本地不可得 | 中 |

### `tengu_api_slow_first_byte`

| key | 出现 | 类型 | 来源 | 敏感等级 |
|---|---:|---|---|---|
| `renderer_mode` | 8/8 | string:8 | 客户端本地不可得 | 低 |
| `subscription_type` | 8/8 | string:8 | 账号 profile 可推导 | 低 |
| `model` | 8/8 | string:8 | 请求体可推导 | 低 |
| `provider` | 8/8 | string:8 | 网关运行时可推导 | 低 |
| `attempt` | 8/8 | int:8 | 网关运行时可推导 | 低 |
| `elapsed_ms` | 8/8 | int:8 | 待分级或客户端本地不可得 | 中 |

## 远程灰度验收与回滚

1. 灰度账号先保持账号级 `auto_telemetry=true`，只选择少量低风险账号验证。
2. 抓远程网关出站 `/api/event_logging/v2/batch`，只保存脱敏统计：event name 分布、`additional_metadata` key 分布、env key 分布、header key/order 摘要、batch size/interval。
3. 对比本目录：重点看 `tengu_api_query` / `success` / `cache_breakpoints` / tool / attachment 的 metadata key 密度是否接近 2.1.195，确认 `requestId=req_*`、`messageID=msg_*`、`queryChainId=uuid` 形态稳定。
4. 敏感字段检查：出站 body 和日志不得包含 prompt、tool input、响应正文、Authorization、Cookie、邮箱、完整账号 UUID。
5. 回滚方式：对异常账号关闭账号级 `auto_telemetry`；如需代码回滚，恢复到本任务前版本后重启服务。该任务没有修改 `/v1/messages` body 顺序，也没有新增数据库迁移。
