# cc2api 非流请求观测与拦截设计

## Technical Design

### 影响范围

目标仓库：`/root/project/cc2api`。

主要改动点：

- `src/store/settings_store.rs`：新增默认 settings key。
- `src/store/db.rs`：迁移补齐默认 settings。
- `src/handler/router.rs`：Settings GET 默认值、PUT 校验、热刷新触发。
- `src/service/gateway.rs`：非流响应日志、非流辅助请求检测和本地响应。
- `web/src/components/Settings.vue`：Settings 页面配置入口。

### 非流响应日志

当前 `forward_to_upstream` 对普通响应直接返回 `resp.bytes_stream()`。要记录非流响应体，需要在满足以下条件时缓冲响应：

- `path.starts_with("/v1/messages")`
- 请求体最终形态 `stream != true`
- `log_non_stream_request_enabled=true`

缓冲后记录：

- `status`
- 响应头脱敏摘要
- 响应体 `safe_body_summary`
- 解码/规范化后的响应体文本，复用 `log_429_request_body_limit` 截断

然后重建 Response 返回给客户端，保持原 status 和非敏感 headers。若响应带压缩编码，优先复用现有 `decode_upstream_error_body` 的 content-encoding 处理思路用于日志，返回给客户端仍使用原始 body，避免改变透传语义。

### 非流辅助请求拦截

归入现有 `WarmupInterceptConfig` / `WarmupInterceptType`：新增类型，例如 `NonStreamAuxiliary`。

初始检测采用“硬条件 + 保护条件 + 排除项”的结构，目标是优先避免误拦用户真实请求。

硬条件全部满足才进入候选：

- `path == "/v1/messages"` 或当前已有的 `/v1/messages` 路由分支命中。
- `client_type == ClientType::ClaudeCode`，由 `User-Agent` 识别 `claude-code/` 或 `claude-cli/`。
- `stream != true`，即非流请求；`stream=false` 和未显式传 `stream` 都按非流处理。
- `max_tokens == 64`。这是当前要拦截的高置信辅助轮询子类，不代表所有非流请求都固定为 64；`8192/64000` 等例外先只观测不拦截。
- 不把 `model` 作为硬条件。`model` 只进入命中日志；后续如需要更保守，可增加可选模型 allow-list，但默认不启用。

保护条件至少满足一个：

- 原始请求体字节数大于等于 `32 KiB`。当前抓包样本最小约 `57 KiB`，`32 KiB` 用于覆盖波动并避开普通短非流请求。
- 或请求正文 text 内容累计长度大于等于 `16 KiB`。

排除项：

- 先执行现有 Haiku probe、Suggestion Mode、标题/Warmup 检测；这些命中时不进入非流辅助请求规则。
- `messages` 为空或最后一条消息不是 `user` 时不拦截，避免覆盖 assistant prefill 或异常请求。
- `model` 不参与默认排除，避免 Fable / 其它 Claude Code 模型下漏拦；是否按模型收窄留给后续显式配置。

请求头处理：

- `X-Stainless-Retry-Count` 不作为硬条件；如果存在且不是 `0`，只在拦截日志中打印，避免 SDK 重试场景因为头缺失或变化导致规则失效。
- `anthropic-beta` / `context-1m-2025-08-07` 不作为命中条件，只进入日志摘要。该 beta 可能由客户端或账号设置产生，不能把辅助请求识别绑定到 1M 开关。

命中后打印结构化日志，至少包含 `type=non_stream_auxiliary`、`account`、`model`、`stream`、`max_tokens`、`body_bytes`、`text_bytes`、`message_count`、`retry_count`、`mode`，不打印原始 prompt。

当前观测补充：

- 最新 3 小时非流日志：53 条里 `max_tokens=64` 为 51 条，`64000` 和 `8192` 各 1 条；因此拦截规则把 `64` 当作当前目标子类条件，而不是非流请求全局事实。
- 最新 3 小时 400 日志：上游错误 message 为 `prompt is too long: ... > 1000000 maximum`，应通过新增非流响应日志继续记录；拦截策略不应默认改写所有 400。

### 非 429 上游错误透传诊断

当前 `forward_request` 在 `status_code >= 400` 时复制上游 status、headers 和 body 直接返回；外层 `handle_request_inner` 对非 429 响应还会统一包一层 `SlotGuardBody`。429 走独立分支，且本地 `AppError::TooManyRequests` 已确认能在 newapi 正常展示。因此不先做大范围错误体格式转换，而是先补齐非 429 错误响应的诊断和必要的响应重建修复。

非流响应日志对 `status >= 400` 额外记录：

- `status`
- `content-type`
- `content-encoding`
- `content-length`
- `transfer-encoding`
- `body_summary`
- 从 JSON 中提取出的 `error.message` / `message`

若确认 `resp.bytes()` 得到的 body 与原响应头存在不一致风险，修复策略为：

- 保留原 HTTP status。
- 保留安全响应头，但在已缓冲重建 body 时移除 `content-length`、`content-encoding`、`transfer-encoding`，由 Axum 重新生成长度/传输语义。
- body 默认保持上游原始错误 JSON，不主动改写 Anthropic 错误体结构。
- 对 429 独立分支保持现状，避免影响已能在 newapi 正常展示的错误。

### 响应模式

新增设置项示例：

- `intercept_warmup_non_stream_aux_enabled=false`
- `intercept_warmup_non_stream_aux_mode=mock_text|error`，默认 `mock_text`
- 可选：`intercept_warmup_non_stream_aux_text=""`，用于固定文本模式。

固定文本模式返回 Anthropic message JSON，复用现有 `mock_warmup_intercept_json_response` 结构。

错误模式返回标准 error object，形如：

```json
{"type":"error","error":{"type":"invalid_request_error","message":"non-stream auxiliary request intercepted locally"}}
```

### UI

在 Settings 页“预热请求拦截”卡片增加“非流辅助请求”开关和响应模式选择。文案说明它会命中 Claude Code 非流 `max_tokens=64` 辅助轮询请求，默认关闭。

### Compatibility

- 默认值关闭，旧实例迁移后行为不变。
- 拦截开启后的默认响应模式是 HTTP 200 固定 assistant 文本，降低 Claude Code 直接报错的概率。
- 非流响应日志默认仍由 `log_non_stream_request_enabled` 控制。
- 日志上限继续复用 `log_429_request_body_limit`。
- 不影响流式响应。

## Rollout / Rollback

- Rollout：先部署但保持新拦截关闭，只开启非流响应日志观察；确认命中特征后再开启拦截。
- Rollback：关闭 `intercept_warmup_non_stream_aux_enabled` 和 `log_non_stream_request_enabled` 即可恢复原转发行为。
