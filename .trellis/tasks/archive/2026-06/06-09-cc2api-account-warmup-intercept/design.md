# cc2api 全局预热请求拦截

## Technical Design

### 配置模型

沿用 `settings` 表，不新增账号字段。建议新增三个布尔字符串 key：

- `intercept_warmup_title_enabled`
- `intercept_warmup_suggestion_enabled`
- `intercept_warmup_haiku_probe_enabled`

布尔值沿用当前 settings 约定：`"true"` / `"false"`。
三个 key 的默认值均为 `"false"`，上线后不改变现有请求行为。

`GatewayService` 启动时从 `SettingsStore` 读取这些 key，并缓存到内存 `RwLock<WarmupInterceptConfig>`；`/admin/settings` 更新后调用 reload 方法即时生效，避免每个请求查库。

### 拦截位置

在 `GatewayService::handle_request_inner` 中完成：

1. 读取请求体并解析 JSON。
2. 检测 `ClientType`。
3. 进入账号选择循环并选中账号后，在 RPM 预占、并发槽位、token 解析、请求改写和上游转发之前执行拦截判断。

选择账号后再拦截可以保持现有 API token 的账号 allow/block 规则和 sticky session 行为一致；但命中拦截后不应占用 RPM、并发槽位或上游连接。

### 识别规则

参考 sub2api 的 `detectInterceptType`：

- Suggestion Mode：最后一条 `messages` 的 `role=user`，首个文本 content 以 `[SUGGESTION MODE:` 开头。
- 标题/预热：
  - 任意文本 content 包含 `Please write a 5-10 word title for the following conversation:`。
  - 任意文本 content 精确等于 `Warmup`。
  - `system` 文本包含 `nalyze if this message indicates a new conversation topic. If it does, extract a 2-3 word title`。
  - `system` 文本包含 `Generate a concise, sentence-case title (3-7 words) that captures the main topic or goal of this coding session`。这是 `data/flows` 中 Claude Code 2.1.156 / 2.1.169 的实际标题生成形态。
- Haiku 探测：
  - `ClientType::ClaudeCode`。
  - `stream` 不是 `true`。
  - `model` 小写后包含 `haiku`。
  - `max_tokens == 1`。

### Mock 响应

非流式返回 Anthropic messages JSON：

- 标题/预热：`id="msg_mock_warmup"`，content text 为 `New Conversation`，`stop_reason="end_turn"`。
- 新版 Claude Code JSON 标题：`id="msg_mock_title"`，content text 为 `{"title":"New Conversation"}`，`stop_reason="end_turn"`。
- Suggestion Mode：`id="msg_mock_suggestion"`，content text 为空字符串，`stop_reason="end_turn"`。
- Haiku 探测：使用仿真 `msg_bdrk_*` 或固定可测试 ID，content text 为 `#`，`stop_reason="max_tokens"`。

流式返回 Anthropic SSE 事件：`message_start`、`content_block_start`、若干 `content_block_delta`、`content_block_stop`、`message_delta`、`message_stop`。

标题/预热内部可拆成两个拦截类型，但对外仍共用 `intercept_warmup_title_enabled`：

- 旧标题/`Warmup` 文本模式返回 `New Conversation`。
- 新版 Claude Code JSON 标题模式返回 `{"title":"New Conversation"}`，因为抓包里的请求带 `output_config.format.type=json_schema`，真实上游输出也是 JSON 对象文本。

不引入泛化 `title`、`conversation`、`session` 关键词匹配；这类关键词在真实对话内容和 assistant 产物中常见，容易误拦截。

### 抓包覆盖结论

`data/flows` 中两组样本共 43 条 `POST /v1/messages?beta=true`：

- 2 条 Haiku 非流式 `max_tokens=1` quota 探测，现有 Haiku 规则覆盖。
- 2 条 `SUGGESTION MODE` 请求，现有 Suggestion 规则覆盖。
- 2 条新版 Claude Code JSON 标题请求，需要新增 system prompt 规则覆盖。
- 旧 sub2api 标题规则 0 命中，但保留作为旧客户端兼容。
- 未发现其它低 token、非流式或高置信预热形态。

### 前端

在设置页新增“预热请求拦截”区块，使用三个独立开关展示对应规则。保存时随现有 `updateSettings` 一并提交。

## Compatibility

- 默认全部关闭，避免上线后改变现有请求行为。
- 不改账号表 schema。
- 不影响 cc2api 自有 `PrimePollerService` 的峰值预热调度，除非它发出的请求也命中全局规则；实现时应明确是否绕过或允许命中。

## Rollout / Rollback

上线后可通过设置页逐项开启。回滚时关闭三个全局开关即可，不涉及数据迁移。
