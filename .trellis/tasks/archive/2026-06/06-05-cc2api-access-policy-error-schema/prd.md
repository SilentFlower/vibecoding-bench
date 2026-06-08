# brainstorm: cc2api 访问策略错误体兼容 new-api

## Goal

让 cc2api 的本地自定义拒绝响应使用 Anthropic / Claude 风格错误体，保证 new-api 作为上游调用方时能识别并展示真实拒绝原因，而不是兜底显示 `status_code=502, Upstream service temporarily unavailable`。

## Background / Known Context

- cc2api 当前已能正确在本地拒绝不符合访问策略的请求，日志会输出 `access policy rejected request`，说明请求没有继续转发到 Anthropic。
- 当前访问策略拒绝响应为 `{"error":"request rejected by access policy","setting":"...","reason":"..."}`，其中 `error` 是字符串。
- `system_role_model_error_response` 也是 cc2api 本地提前拒绝，当前响应为 `{"error":"messages[].role=system is not allowed for this model", ...}`，同样属于需要兼容 new-api 的本地自定义错误体。
- new-api 的 `RelayErrorHandler` 只会把 `error` 为对象且包含 `message` 的响应识别为标准上游错误；字符串型 `error` 会进入兜底路径，最终可能被包装成通用 502 文案。
- cc2api 的 `AppError::TooManyRequests("all accounts are busy")` 走通用错误响应，当前在 new-api 中能正常显示，说明本任务重点是访问策略自定义错误体格式。
- 目标代码仓库是 `/root/project/cc2api`，父仓 `/root/project/vibecoding-bench` 只保存 Trellis 任务记录。

## Requirements

- 访问策略拒绝响应必须改为标准错误对象格式，至少包含 `error.message` 和 `error.type`。
- system role 模型白名单拒绝响应必须改为同样的标准错误对象格式。
- 响应顶层必须保留 `type: "error"`，对齐 Anthropic / Claude 错误响应习惯。
- 访问策略 HTTP 状态码保持 `403 Forbidden`，system role 模型白名单 HTTP 状态码保持 `400 Bad Request`。
- 错误 message 必须包含当前真实拒绝原因，例如版本不在范围、UA 不在白名单、缺少 User-Agent。
- 可以保留 `setting`、`reason`、`model`、`allowed_system_role_models` 等 cc2api 调试字段，但不能破坏标准 `error` 对象。
- 不改变访问策略匹配规则、不改变默认版本范围、不改变 UA 白名单。
- 不改变 system role 模型白名单规则。
- 不修改 new-api。
- 不新增 debug 模式或更详细请求体日志。
- 不改上游透传错误、不改 account busy / 429 行为。

## Acceptance Criteria

- [ ] 使用不允许的 Claude Code 版本请求时，cc2api 返回 HTTP 403，body 形如 `{"type":"error","error":{"type":"invalid_request_error","message":"..."},...}`。
- [ ] 使用不允许的非 Claude User-Agent 请求时，cc2api 返回 HTTP 403，`error.message` 展示 UA 白名单拒绝原因。
- [ ] 使用不允许 system role 的模型请求时，cc2api 返回 HTTP 400，body 形如 `{"type":"error","error":{"type":"invalid_request_error","message":"..."},...}`。
- [ ] new-api 读取该响应时能按 `error` 对象解析出 message，不再因为 `error` 为字符串走兜底。
- [ ] 现有访问策略单测更新并通过。
- [ ] `cargo test --offline access_policy` 通过；可用时执行更广的 `cargo test --offline` 或 `cargo check --offline`。

## Out of Scope

- 修改 new-api 的错误处理逻辑。
- 调整渠道状态码映射、多渠道重试策略或账号 busy 行为。
- 改动访问策略配置 UI、数据库 schema 或默认配置。
- 改动上游响应透传逻辑。
