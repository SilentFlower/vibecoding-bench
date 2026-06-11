# cc2api Auto Mode classifier 设计

## Technical Design

### 影响范围

- `/root/project/cc2api/src/store/settings_store.rs`
- `/root/project/cc2api/src/store/db.rs`
- `/root/project/cc2api/src/handler/router.rs`
- `/root/project/cc2api/src/service/gateway.rs`
- `/root/project/cc2api/web/src/components/Settings.vue`

### Settings Contract

新增两个 settings key，默认均为 `passthrough`：

- `intercept_auto_mode_classifier_stage1_mode`
- `intercept_auto_mode_classifier_stage2_mode`

枚举值：

- `passthrough`：识别后仍转发上游。
- `mock_allow`：本地返回 Anthropic message JSON，文本 `<block>no</block>`。
- `mock_block`：本地返回 Anthropic message JSON，文本 `<block>yes</block><reason>blocked by local policy</reason>`。
- `error`：本地返回标准 error object。

配置通过 `GatewayService::reload_warmup_intercept_config()` 热刷新，沿用现有预热与 classifier 本地处理配置缓存，避免请求热路径查库。

旧版通用“非流辅助请求”配置不再保留：

- `intercept_warmup_non_stream_aux_enabled`
- `intercept_warmup_non_stream_aux_mode`

迁移会删除历史 settings 行，`/admin/settings` 返回前也会过滤这些旧 key，避免前端或外部调用继续依赖旧配置。

新增流式稳定性 settings，默认不改变现有行为：

- `stream_keepalive_enabled=false`
- `stream_keepalive_interval_secs=45`
- `stream_upstream_idle_timeout_secs=120`

`stream_keepalive_interval_secs` 在 API 层校验 `5..240`；`stream_upstream_idle_timeout_secs` 校验 `30..1800`。配置通过 `GatewayService::reload_stream_stability_config()` 热刷新，并缓存到 `StreamStabilityConfig`。

### Detection

先执行现有 Haiku probe、Suggestion Mode、标题/Warmup 检测；这些命中或疑似命中时不进入 classifier 规则。

公共硬条件：

- `path == "/v1/messages"`。
- `client_type == ClientType::ClaudeCode`。
- `stream != true`。
- 最后一条 message 为 `user`。
- 请求 text 内容包含 `<transcript>` 和 `</transcript>`。
- system/user text 中包含 XML output format 相关标记：`<block>yes</block>` 与 `<block>no</block>`。

Stage 1：

- `max_tokens == 64` 或 `max_tokens == 256`。
- `max_tokens == 64` 时，`stop_sequences` 包含 `"</block>"` 即命中；旧 `Err on the side of blocking. <block> immediately.` suffix 只作为兼容信号，避免 prompt 尾部微调导致漏命中。
- `max_tokens == 256` 是 Claude Code fast-only Stage 1 形态，可能不带 `stop_sequences`，满足公共 XML classifier 结构即命中。
- 不把 `temperature=0` 或 exact suffix 作为硬条件，因为实际抓包与源码形态会随 CLI/feature flag 微调。

Stage 2：

- `4096 <= max_tokens <= 8192`。
- 不要求 exact Stage 2 suffix；满足公共 XML classifier 结构即可，避免 CLI prompt 尾部微调导致漏命中。
- 如 `stop_sequences` 包含 `"</block>"`，则不视为 Stage 2，因为这是 Stage 1 immediate decision 的强信号。

`model`、`anthropic-beta`、body 大小只用于日志，不作为默认硬条件。

### Response Shape

本地 mock 返回 Anthropic `/v1/messages` 兼容 JSON：

```json
{
  "id": "msg_mock_auto_mode_classifier_stage1",
  "type": "message",
  "role": "assistant",
  "model": "<request model or claude-mock>",
  "content": [{"type": "text", "text": "<block>no</block>"}],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 0, "output_tokens": 1}
}
```

Stage 2 使用 `msg_mock_auto_mode_classifier_stage2`。`mock_block` 文本为 `<block>yes</block><reason>blocked by local policy</reason>`。

错误模式复用标准 error object，code 使用 `auto_mode_classifier_intercepted`，避免伪装成上游 200。

### Logging

命中 classifier 时输出结构化日志：

- `type`: `auto_mode_classifier_stage1` / `auto_mode_classifier_stage2`
- `action`: `passthrough` / `mock_allow` / `mock_block` / `error`
- `account_id`
- `model`
- `max_tokens`
- `body_bytes`
- `text_bytes`
- `message_count`
- `retry_count`
- `mode`

不输出原始 prompt、Authorization、Cookie、token。

流式 keep-alive 注入时输出 `stream_keepalive_injected`，包含 account、chunks、max_gap_ms 和配置间隔，不输出 prompt 或响应正文。

### Streaming Keep-Alive

流式响应包装层替换原先的固定 `.timeout(UPSTREAM_STREAM_IDLE_TIMEOUT)` 链式逻辑，统一通过 `stable_upstream_stream()` 处理：

- 默认关闭 keep-alive 时，行为保持历史等价：超过 `stream_upstream_idle_timeout_secs` 未收到上游 chunk 后向下游返回 timeout 错误。
- 开启 keep-alive 时，上游首个 chunk 到达前只等待上游，不插入任何字节，避免影响首字时间。
- 首个真实 chunk 之后，如果连续 `stream_keepalive_interval_secs` 没收到上游 chunk，则向下游写入 SSE comment `: cc2api-keepalive\n\n`。
- heartbeat 不是 `data:` 事件，也不是 Anthropic `{"type":"ping"}`，不会进入业务事件流。
- 每次真实上游 chunk 到达后重置间隔计时；上游静默超过 `stream_upstream_idle_timeout_secs` 仍按错误中断。

### Compatibility

- 默认 `passthrough`，旧实例迁移后行为不变。
- 转发型非流 `/v1/messages` 与流式请求共用同一条 `rewrite_body_with_stateful_completion()` / `rewrite_headers()` 链路，继续覆盖 2.1.172 的 `cc_version`、`cch`、UA、`anthropic-beta`、Stainless 头；CCH 在最终 body 字节上计算，不按 `stream` 分支跳过。
- 本地 mock / error 的 Auto Mode classifier 请求不进入上游转发链路，不需要生成上游签名和上游请求头。
- 只拦截强命中 classifier 的非流 `/v1/messages`，不处理 `64000` fallback。
- `64000` fallback 不直接拦截；通过可选流式 keep-alive 降低 watchdog fallback 触发概率。
- 保留现有非流响应日志和响应解码修复。

## Rollout / Rollback

- Rollout：先部署默认 `passthrough`，观察 classifier 命中日志；确认后仅开启 Stage 1 `mock_allow`，再评估 Stage 2。
- Rollback：把两个新模式都设回 `passthrough`。
