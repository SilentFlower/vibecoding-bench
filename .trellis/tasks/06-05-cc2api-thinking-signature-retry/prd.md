# cc2api thinking signature retry

## Goal

在 `/root/project/cc2api` 的 `/v1/messages` 官方 Anthropic 转发链路中，增加 thinking signature 相关 400 的自动降级重试，行为对齐 `/root/project/sub2api` 的 Antigravity/Claude 请求处理：当上游返回 `Invalid signature in thinking block` 等签名相关错误时，不把原始 400 直接透给客户端，而是先清理 signature-sensitive 历史块后重试，降低从 Kiro/Antigravity 等渠道切回官方 Anthropic 时的会话历史污染问题。

## Background / Known Context

- 用户观察到从 Kiro 渠道的 Claude 切回官方渠道后，偶发 `status_code=400`，错误包含 `Invalid signature in thinking block`。
- Anthropic `thinking.signature` 是不透明字段，`cc2api` 不能验证、修复或重算签名。
- `/root/project/sub2api` 的 Antigravity/Claude 链路已有参考实现：
  - 首次上游 400 且错误消息命中 signature/thought_signature/thinking 结构问题后触发整流。
  - 第一阶段 `thinking-only`：关闭顶层 `thinking`，将 `content[]` 中 `type=thinking` 转普通 `text`，删除 `redacted_thinking`。
  - 第二阶段 `thinking+tools`：如果第一阶段仍然 signature 相关 400，再额外将 `tool_use` / `tool_result` 转普通 `text`。
- `cc2api` 当前在 `src/service/gateway.rs` 完成账号选择、请求体/header 改写、上游转发、429 换号和遥测记录；`src/service/rewriter.rs` 负责 body/header 改写。
- `cc2api` 当前没有专门处理 `thinking.signature` 的 sanitizer 或重试逻辑。

## Requirements

- 仅针对 `/v1/messages` 的官方 Anthropic 转发响应做处理。
- 当上游响应为 HTTP 400，且错误体包含 signature 相关错误时，触发签名整流重试。
- signature 相关错误识别必须覆盖：
  - `signature`
  - `thought_signature`
  - `Invalid signature in thinking block`
  - `thinking` / `redacted_thinking` 结构类错误，例如 `Expected thinking or redacted_thinking`
- 重试行为必须对齐 `sub2api` 的 Antigravity/Claude 处理：
  - 第一阶段 `thinking-only`：移除顶层 `thinking` 配置；把历史 message content 中的 `type=thinking` 转成 `type=text`，保留 `thinking` 文本；删除 `redacted_thinking`；遇到无 `type` 但有 `thinking` 字段的块，也转成普通 text。
  - 第一阶段仍返回 signature 相关 400 时，进入第二阶段 `thinking+tools`。
  - 第二阶段在第一阶段基础上，额外把 `tool_use` 和 `tool_result` 转成普通 text，优先保证请求可被官方上游接受。
- 每个原始上游请求最多触发两次整流重试，不能无限循环。
- 整流重试必须复用同一个已选账号、同一个 upstream token、同一套改写后 headers 的语义，不能重新进入账号选择并改变会话路由。
- 第一阶段或第二阶段成功后，向客户端返回成功响应；若仍失败，返回最后一次上游响应。
- 429 换号逻辑继续保持现有行为；签名整流不应扩大到 429。
- 遥测应记录最终返回结果，并能在安全摘要里区分是否发生过 signature retry，避免记录 thinking 原文、token、prompt、请求体/响应体全文。
- 错误日志可以记录阶段名、账号 ID、状态码、上游 request id、错误类型，但不能记录完整请求体、响应体、thinking 内容或签名原文。
- Gemini `thoughtSignature` 的 dummy 值 `skip_thought_signature_validator` 不能用于 Anthropic `thinking.signature`。

## Acceptance Criteria

- [ ] 构造包含 `messages[].content[].type=thinking` 且 `signature` 无效的请求，上游第一次返回 signature 相关 400 时，`cc2api` 会用 `thinking-only` 清理后的 body 重试一次。
- [ ] 若 `thinking-only` 重试成功，客户端收到成功响应，原始 signature 相关 400 不外泄为最终结果。
- [ ] 若 `thinking-only` 仍返回 signature 相关 400，`cc2api` 会进行 `thinking+tools` 第二阶段重试。
- [ ] 第二阶段会把 `tool_use` / `tool_result` 转为普通 text；若成功，客户端收到成功响应。
- [ ] 若两阶段都失败，客户端收到最后一次上游响应；不会无限重试。
- [ ] 非 signature 相关 400 不触发整流重试，保持原有错误透传/处理行为。
- [ ] 非 `/v1/messages` 请求不触发整流重试。
- [ ] 单元测试覆盖 signature 错误识别、thinking-only 转换、thinking+tools 转换、两阶段重试流程。
- [ ] 不保存或输出请求体全文、响应体全文、thinking 内容、签名原文、token。
- [ ] 现有 `npm --prefix web run build` 仍通过；Rust 校验在本机工具链可用时运行 `cargo fmt --check` 和相关单测。

## Notes

- 本任务只迁移 Antigravity/Claude 风格的签名重试思路，不尝试破解 Anthropic `thinking.signature`。
- 本任务不实现 Kiro 渠道来源识别、不新增跨渠道会话存储、不实现 Gemini native `thoughtSignature` dummy 注入。
