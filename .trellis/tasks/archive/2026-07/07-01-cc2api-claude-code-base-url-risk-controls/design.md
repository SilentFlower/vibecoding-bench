# Design: cc2api Claude Code base URL 风险控制

## Scope

本设计只覆盖 `cc2api/`：Rust 后端网关热路径、telemetry sanitizer、settings 链路、Vue 设置页和测试。`vibecoding-bench` worker 默认 Claude Code 版本已在前序变更中独立处理，不纳入本任务。

## Architecture

### Setting

新增 setting：

```text
claude_code_context_sanitizer_mode = off | report_only | normalize
默认值: report_only
```

同步位置：

```text
src/store/settings_store.rs
src/store/db.rs
src/handler/router.rs
src/service/gateway.rs
web/src/components/Settings.vue
```

`GatewayService` 持有 `RwLock<ClaudeCodeContextSanitizerConfig>`，请求热路径只读内存，不查 DB。

### Request path

`GatewayService` 解析 body 后，现有流程会调用 `Rewriter::rewrite_messages(...)`，随后序列化最终 body，并调用 `refresh_cch_attestation(...)`。

新增流程应位于 Claude Code 客户端模式的 `rewrite_messages` 中，且在 `refresh_billing_attestation` 之前完成：

```text
incoming JSON body
  -> detect_client_type
  -> rewrite_messages(..., context_sanitizer_config)
       -> rewrite metadata/user_id/system prompt
       -> scan currentDate markers
       -> normalize only when mode=normalize
  -> serialize final body
  -> refresh CCH / cc_version attestation
  -> upstream
```

为了避免把 `GatewayService` 的 setting 细节塞进 `Rewriter` 外部调用过多，设计上新增一个小型配置结构和公共入口，例如：

```rust
pub enum ClaudeCodeContextSanitizerMode { Off, ReportOnly, Normalize }
pub struct ClaudeCodeContextSanitizerConfig { pub mode: ClaudeCodeContextSanitizerMode }
```

`GatewayService` 从 setting reload 出该结构，调用 rewriter 时传入。

### Scan target

扫描对象：

- `body.system`：string 或 array text block。
- `messages[].content`：string 或 array text block。

命中规则以精确为主：

- 文本包含 Claude Code 自动注入日期句式，类似 `Today's date is YYYY-MM-DD.`。
- 撇号允许 ASCII `'`、RIGHT SINGLE QUOTATION MARK、MODIFIER LETTER APOSTROPHE、MODIFIER LETTER PRIME。
- 日期允许 `YYYY-MM-DD` 或 `YYYY/MM/DD`。
- 命中时生成 `ContextSanitizerFinding`：字段路径、日期、撇号类别、分隔符类别、text_len、text_hash。

规范化只替换该句式，不替换整段文本其它内容。初版不解码 Claude Code 内部域名表，也不判断 hostname；只处理已经进入请求体的可疑输出形态。

### Logging

日志要求：

- 使用 `warn!` 或 `info!` 的结构化字段。
- 不输出 `text` 原文。
- 字段建议：`mode`、`action`、`path`、`date_separator`、`apostrophe_variant`、`text_len`、`text_hash`、`client_type`。
- `off` 不扫描不日志；`report_only` 命中只日志；`normalize` 命中日志并修改。

### Telemetry sanitizer

现有 `sensitive_field_reason` 统一判断 key/value 是否丢弃。扩展点：

- `sensitive_key` 增加 base URL / gateway / proxy / host 相关 key。
- 新增 value 判断 `looks_like_proxy_or_gateway_url(text)`，仅命中非官方 URL 或显式 proxy/gateway/base-url 语义时返回 `proxy_gateway_value`。
- 保留 `api.anthropic.com`、`anthropic.com`、`claude.ai` 等官方 host 的正常字段，避免误删公开端点字段。

### Frontend

在 `Settings.vue` 现有“环境字段透传”或“Anthropic 缓存改写”附近新增一个卡片或小节：

- 标题：`Claude Code 上下文风险控制`
- 单选项：`关闭`、`仅观测`、`观测并规范化 currentDate`
- 文案强调默认只观测，normalize 会修改请求体。

字段保存到 `claude_code_context_sanitizer_mode`。

## Compatibility

- 默认 `report_only` 不改变请求体，只增加脱敏日志和 telemetry 清洗。
- `normalize` 是显式开关，会改变请求体；必须在 CCH 刷新前执行。
- 不修改版本画像、账号 canonical env、CCH seed、beta 列表或 bootstrap 行为。
- 新 setting 走 settings 默认值插入，不需要账号迁移。

## Risks

- currentDate 命中规则过宽会误改用户正文：通过限定日期句式、只替换句子、不处理任意 `Today` 文本降低风险。
- 日志泄露 prompt：所有日志只输出 hash/长度/路径。
- telemetry value 识别误删官方端点：官方 Anthropic host 加 allowlist。
