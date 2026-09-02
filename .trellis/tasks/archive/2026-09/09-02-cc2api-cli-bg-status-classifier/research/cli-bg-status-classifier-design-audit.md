# Research: cli-bg 状态分类器设计复核

- Query: 复核 Claude Code 2.1.257 `cli-bg` JSON 状态分类请求的强特征检测、identity-only 放行、mock 响应和经 cc2api 账号代理链路的生产 A/B 验收方法。
- Scope: internal
- Date: 2026-09-02

## Files Found

- `cc2api/src/service/gateway.rs`：请求热路径、现有 classifier 拦截、账号选择、OAuth 注入、上游转发与 429 日志。
- `cc2api/src/service/rewriter.rs`：Claude Code / API 客户端识别、header 画像、messages 正文改写、metadata identity 与 cache_control 处理。
- `cc2api/src/tlsfp/tlsfp.rs`：按账号 `proxy_url` 创建带 Node.js TLS 指纹的上游客户端。
- `cc2api/src/model/api_token.rs`、`cc2api/src/store/token_store.rs`、`cc2api/src/handler/router.rs`：可限制到单账号的临时网关 token 及管理接口。
- `.trellis/spec/cc2api/backend/service-architecture.md`：Gateway 热路径、账号/session/拦截顺序和敏感日志边界。
- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`：2.1.257 Fable 5.1 画像、Auto Mode classifier 的可信区检测原则和抓包落盘限制。
- `.trellis/tasks/09-02-upgrade-claude-code-2-1-257/research/fable-5-1-capture-summary.md`：2.1.257 Fable 5.1 原始画像、`[1m]` 行为及新 endpoint 观察。
- `.trellis/tasks/09-02-upgrade-claude-code-2-1-257/research/fable-5-1-online-compatibility-audit.md`：线上配置、Fable 5.1 限制与首字节超时结论。

## Findings

### 1. 强特征检测边界

建议新增独立检测入口，显式接收原始 headers，例如：

```text
detect_cli_bg_status_classifier_request(path, headers, body, client_type) -> bool
```

必须同时满足以下条件，任一不满足即失败开放，进入普通转发：

1. `path == "/v1/messages"`，不能用宽泛前缀；现有 Auto Mode 公共检测也是精确路径（`cc2api/src/service/gateway.rs:4146`）。
2. `client_type == ClientType::ClaudeCode`；客户端类型只由 `claude-code/` 或 `claude-cli/` UA 前缀确认（`cc2api/src/service/rewriter.rs:5131`）。
3. 原始 header 的 `x-app` 大小写不敏感查找后，值精确为 `cli-bg`。这是本请求与普通 `x-app=cli` 消息最强的通道特征；检测必须发生在 header rewrite 前。Claude Code header 白名单已保留 `x-app`（`cc2api/src/service/rewriter.rs:1154`、`cc2api/src/service/rewriter.rs:1166`），默认分支会原值透传（`cc2api/src/service/rewriter.rs:1239`），因此不能在放行分支把它改回 `cli`。
4. `model == "claude-fable-5-1"` 精确匹配。不要用 `starts_with("claude-fable-")`，也不要自动纳入 `claude-fable-5` 或 `[1m]`；现有协议规范已要求 wire profile 按精确模型 ID 选择，抓包也表明 `[1m]` 入口最终落为标准 `claude-fable-5-1` message 请求。
5. 非流式，且 `max_tokens == 3072`。当前 helper 将缺失或 `false` 的 `stream` 都视为非流式（`cc2api/src/service/gateway.rs:4334`），与抓包结构一致。
6. `system` 的可信文本同时包含三组稳定语义标记，而不是匹配整段 prompt：
   - `A user kicked off a Claude Code agent`
   - `THE FOUR STATES`
   - `OUTPUT`、`respond with ONLY this JSON`，并同时出现 `state`、`detail`、`tempo`、`needs`、`output`
7. messages 必须恰好一条、role 为 `user`、content 为单个文本值；文本需以 `Current state:` 开始，并包含 `Tool calls so far:`、`User's most recent ask:`、`Assistant message tail` 标签。现有 `single_text_from_content` 已支持字符串或单 text block（`cc2api/src/service/gateway.rs:4409`），可复用其语义。
8. 建议再要求 `system` 恰好一个 text block，且该 block 的 `cache_control.type == "ephemeral"`；允许 `ttl` 缺失或为抓包值，不把 TTL 当业务识别条件。这样可避免普通会话把 classifier 文案作为多个 system 文档之一时误命中。

检测只从 system 读取分类协议，从唯一 user message 读取待分类数据；禁止使用 `request_text_items` 扫描所有文本，因为用户 transcript 可能复制整段 classifier prompt。现有 Auto Mode 已明确区分可信 system / transcript 外指令，并避免被 transcript 内容污染（`cc2api/src/service/gateway.rs:4157`、`cc2api/src/service/gateway.rs:4171`、`cc2api/src/service/gateway.rs:4198`）。也不建议绑定完整 prompt hash、精确字符数或完整英文句子，否则 2.1.257 的微小文案变化会漏命中。

检测位置应在原始 `body_map` / headers 可用之后、账号 admission 之前计算一次；mock 可直接返回，不消耗账号槽位/RPM。现有 warmup classifier 位于账号选择后但 admission 前（`cc2api/src/service/gateway.rs:1571`、`cc2api/src/service/gateway.rs:1647`）。若需要完全不选账号，检测与 mode 读取可前移到 session hash / 账号选择前；若 mock 响应日志需要 account_id，则保留现有位置，但仍不得进入 admission。

### 2. Passthrough 应为 identity-only body rewrite

当前通用 `/v1/messages` 正文链路会依次执行：空 text 清理、messages identity/system/context 改写、message cache 断点重打、已有 ephemeral TTL 改写、disabled thinking 改写和可选 CCH 重算（`cc2api/src/service/rewriter.rs:1442`、`cc2api/src/service/rewriter.rs:1486`）。其中线上结构差异已经直接观察到 message cache breakpoint 被新增、system cache TTL 从原始 ephemeral 改为 `1h`；对应实现分别位于 `cc2api/src/service/rewriter.rs:2746`、`cc2api/src/service/rewriter.rs:2789`、`cc2api/src/service/rewriter.rs:4885`、`cc2api/src/service/rewriter.rs:4894`。这两项是当前 429 的首要嫌疑，但因上游只返回泛化 `rate_limit_error/Error`，因果仍需 A/B 证实。

放行模式最小正文行为应是独立的 identity-only 路径，不要把多个全局 setting 临时改成 off：

- 保留 `metadata.user_id` 中所选账号的 `device_id`、`account_uuid` 替换；有真实 session 且账号 session pool 生效时，保留 `session_id` 映射。现有替换逻辑在 `cc2api/src/service/rewriter.rs:1575`，JSON identity 的三个字段写入在 `cc2api/src/service/rewriter.rs:1593`，legacy identity/session 兼容在 `cc2api/src/service/rewriter.rs:1620`。
- 保留 `build_upstream_session_rewrite`，因为它在 admission 后按所选账号解析真实 session 到 upstream session 的映射（`cc2api/src/service/gateway.rs:497`、`cc2api/src/service/gateway.rs:505`）；保留 `align_mapped_upstream_session_header`，让 body 与 `X-Claude-Code-Session-Id` 一致（`cc2api/src/service/gateway.rs:1788`）。
- identity-only 返回 `stateful_cache_completion=None`，不能推进本地 stateful cache；该 completion 本来描述最终发送正文的 cache anchors（`cc2api/src/service/gateway.rs:2034`）。
- 使用结构化 JSON 修改 identity 并重新序列化；项目启用了 `serde_json/preserve_order`（`cc2api/Cargo.toml:30`），可保持已有对象字段相对顺序。不要用字符串替换 metadata JSON，避免转义或同名文本误改。

必须绕过的正文行为：

- `strip_empty_text_blocks`。
- `rewrite_system_prompt`，包括 billing、platform、Shell/OS/cwd 改写。
- `scrub_git_user_in_reminders` 与 currentDate sanitizer。
- 全部 message cache_control 删除、排序、重打与 stateful 状态。
- 全部现有 cache_control TTL 改写；原始 `{"type":"ephemeral"}` 必须原样保留，不新增 `ttl`。
- `rewrite_disabled_thinking_to_adaptive`。
- API mimicry 字段增删、stream/max_tokens/fallback/thinking/body-order 逻辑；强检测已限定 Claude Code 客户端，本就不应进入 API 分支。
- CCH 计算或刷新。该 classifier 抓包没有 billing header；强检测可以额外拒绝带 `x-anthropic-billing-header` / `cch=` 的变体，避免绕过未来真正需要 attestation 的请求。

必须保留的代理能力都位于 identity-only 正文以外：

- 原网关 token 鉴权和 allowed/blocked account 过滤（`cc2api/src/service/gateway.rs:1482`）。
- 账号选择、sticky、并发槽位、RPM admission 与 429 账号级策略（`cc2api/src/service/gateway.rs:1501`、`cc2api/src/service/gateway.rs:1647`）。
- `rewrite_headers` 的 Claude Code 画像、beta/版本/组织字段和原始 `x-app=cli-bg` 透传（`cc2api/src/service/gateway.rs:1778`、`cc2api/src/service/rewriter.rs:1186`、`cc2api/src/service/rewriter.rs:1250`）。
- 账号 OAuth token 的内部解析和最终 Authorization 覆盖；下游永远不需要接触账号 token（`cc2api/src/service/gateway.rs:1810`、`cc2api/src/service/gateway.rs:1835`）。
- `forward_request` 通过 `account.proxy_url` 获取 TLS 指纹客户端并发送（`cc2api/src/service/gateway.rs:2229`、`cc2api/src/service/gateway.rs:2233`、`cc2api/src/service/gateway.rs:2244`）；代理 client 在 `proxy_url` 非空时显式配置 reqwest proxy（`cc2api/src/tlsfp/tlsfp.rs:397`、`cc2api/src/tlsfp/tlsfp.rs:412`）。这满足“必须走账号代理”，不能用服务器本地 curl 直连 Anthropic 代替验收。
- 成功/失败 telemetry、响应透传和账号级重试保持原链路。注意用于验收的临时网关 token应固定单账号，防止一个 classifier 429 被多账号放大。

### 3. Mock 响应约束

mock 必须返回 HTTP 200、`Content-Type: application/json` 的 Anthropic non-stream Message envelope。现有 `mock_text_message_response` 已给出兼容形状（`cc2api/src/service/gateway.rs:4531`）：

```json
{
  "id": "msg_mock_cli_bg_status_classifier",
  "type": "message",
  "role": "assistant",
  "model": "claude-fable-5-1",
  "content": [{"type": "text", "text": "{...}"}],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "output_tokens": 1
  }
}
```

`content[0].text` 必须是 JSON 字符串，不是嵌套 JSON 对象，也不能包 Markdown fence；反序列化后必须精确满足 classifier schema：

```json
{"state":"working","detail":"...","tempo":"active","output":{}}
```

- `state` 只允许 `working|blocked|done|failed`。
- `tempo` 只允许 `active|idle|blocked`，blocked 时必须为 `blocked`。
- `detail` 一行且控制在约 64 字符内。
- `needs` 只在 blocked 时存在，其他状态必须省略。
- `output` 始终是对象；working 通常 `{}`，完成态可含不超过 180 字符的 `result`。
- `model` 原样回显请求模型；`stop_reason=end_turn`；cache usage 为 0。`output_tokens` 可沿用现有文本估算 helper，不依赖真实计费。

本地分类应只消费唯一 user message 中的 `Current state` 与 tail；优先执行 prompt 已定义的显式 markers 和 API/auth/infra error 规则，再处理 `Next check` / 明确未来动作、用户 gate、完成态。解析失败必须采取保守且不中断工作流的确定性 fallback，并写结构化脱敏日志；不要把整段 tail 放进日志。静态永远返回 `done` 或 `working` 会分别造成漏通知或永不完成，不能作为正式 mock 实现。

### 4. 经 cc2api 账号代理链路的生产 A/B

推荐按“旧行为基线 -> 新 passthrough -> mock -> 恢复 passthrough”执行，所有请求都打生产 cc2api 的 `/v1/messages`，禁止直接请求 `api.anthropic.com`：

1. 使用完全合成的 classifier payload：保留官方 system 稳定 markers 和真实结构，user 内容只写虚构的 `Current state`、tool count、ask 与 assistant tail，不使用任何真实会话 prompt。
2. 通过 `/admin/tokens` 创建一次性 gateway token，并用 `allowed_accounts` 固定一个已确认走代理的账号。创建接口返回 token（`cc2api/src/handler/router.rs:701`、`cc2api/src/handler/router.rs:708`），网关会据此只保留允许账号（`cc2api/src/service/gateway.rs:1482`）。验收结束立即删除该 token。
3. token 和 synthetic body 只保存在当前非交互 shell 变量/匿名 pipe 或 fd 中；不要作为 curl 命令行参数、不要写临时文件、不要 `set -x`、不要回显响应中的 token。账号 OAuth token完全由 cc2api 内部解析并替换 Authorization，无需读取数据库 token。
4. 在旧版本上先发一次同 payload，记录且只记录：时间、HTTP status、脱敏 upstream request id、响应体 SHA/字节数；预期复现 429。若旧版本已经无法保留，不为制造对照而重新部署旧镜像，可用现存 429 结构证据作为基线。
5. 部署新版本，设置默认 `passthrough`，发同 payload；预期检测日志为 `mode=passthrough`，上游 status 非 429。日志只记录 model、stream、max_tokens、x-app 是否命中、body 前后字节数和短 SHA、account_id，不记录 system/user 文本。
6. 临时切换为 `mock`，再发同 payload；预期本地 HTTP 200、Message envelope 合法、`content[0].text` 可二次解析，且没有对应 upstream request id / 账号 RPM 增量。随后立即恢复 `passthrough`。
7. 再发一个最小反例，例如只把 `x-app` 改为 `cli` 或删除一个 system marker；预期不命中专用分支，证明不会误伤普通 Fable 请求。不要在生产用真实业务 prompt 做负例。
8. 验收前关闭 `log_429_request_enabled` 和 `log_non_stream_request_enabled`，或至少把 body limit 置 0，验收后恢复原值。当前请求捕获会递归隐藏 token 字段，但普通 system/user 文本仍会保留（`cc2api/src/service/gateway.rs:3009`、`cc2api/src/service/gateway.rs:3031`、`cc2api/src/service/gateway.rs:3080`），不满足“完整 prompt 不落盘”的要求。普通 summary 只输出长度与短 SHA（`cc2api/src/service/gateway.rs:2862`），可以保留。

对“走代理”的验收不能只看 HTTP 200。应在不打印代理 URL 的前提下记录选中 account_id，并确认该账号 `proxy_url` 非空；代码层证据是 `forward_request -> get_request_client(&account.proxy_url)`。如要做运行时强证明，可临时增加仅记录 `proxy_configured=true/false` 的结构化字段，禁止记录代理 URL、用户名或密码。

## Related Specs

- `.trellis/spec/cc2api/backend/service-architecture.md`：Gateway 热路径必须明确拦截/admission 顺序，session pool 只影响最终上游 body/header，sticky/RPM 使用真实下游 session；日志不得包含完整 session 或请求体。
- `.trellis/spec/cc2api/backend/settings-database.md`：新增全局 setting 需要默认值、非法值兜底、SQLite/PostgreSQL 一致和运行时热加载。
- `.trellis/spec/cc2api/backend/testing-quality.md`：协议热路径需要正反例、完整 cargo test 和必要的 CCH 回归。
- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md`：classifier 协议从可信区识别、冲突时失败开放；Fable 5.1 按精确 ID 建模；禁止提交 token、完整抓包和完整 prompt。

## Caveats / Not Found

- 尚无上游错误体明确指出“TTL 或 message cache breakpoint 导致 429”；当前结论来自同一请求在 cc2api 前后结构差异和 288 次一致的请求级 429，必须靠生产 A/B 最终确认。
- 当前代码没有 `cli-bg` JSON 状态分类器专用类型或 setting；现有 Auto Mode classifier 是 XML Block/Severity 协议和不同 token 区间（`cc2api/src/service/gateway.rs:4109`），不能复用其检测结果或 mock 文本，只能复用 mode/settings/envelope 模式。
- identity-only 路径仍会因为结构化 metadata 替换而重新序列化 body；`preserve_order` 能保持 JSON 对象字段顺序，但不会保留原始空白。若 identity-only 仍返回 429，下一轮应 A/B “完全原始 body”与“identity-only body”，但完全原始 body 可能造成 OAuth 账号与 metadata identity 不一致，不能直接作为默认实现。
- 临时 token 当前以明文存储并可由管理接口返回（`cc2api/src/store/token_store.rs:53`、`cc2api/src/store/token_store.rs:108`）；因此生产验收必须短时创建、固定单账号、结束即删除，且不能把管理响应写日志或文件。
