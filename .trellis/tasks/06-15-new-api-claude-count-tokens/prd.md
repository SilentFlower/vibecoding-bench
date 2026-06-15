# new-api 支持 Claude count_tokens 透传

## Goal

在 `/root/project/new-api` 中补齐 Claude 原生 `POST /v1/messages/count_tokens` 的专用透传能力，让 Claude Code `/context` 经过 new-api 再到 cc2api/Anthropic 时能拿到 `{"input_tokens": number}`，避免 count_tokens 在 new-api 入口失败后触发 Claude Code 的 `messages.create(max_tokens=1, stream=false)` fallback。

## Background / Known Context

- cc2api 直连已经支持 `POST /v1/messages/count_tokens?beta=true`，远程容器日志能看到 `count_tokens_forward`，且最近复测没有 `count_tokens upstream error`。
- 经过 new-api 时仍“不太正常”：`/root/project/new-api/router/relay-router.go` 目前只注册 `POST /v1/messages`，没有 `POST /v1/messages/count_tokens`。
- Claude Code 使用 `@anthropic-ai/sdk@0.39.0`，`anthropic.beta.messages.countTokens()` 会请求 `/v1/messages/count_tokens?beta=true`，并把 `token-counting-2024-11-01` 放进 `anthropic-beta` header。
- Claude Code 的 `countMessagesTokensWithAPI()` 只要 count_tokens 抛错、非 2xx，或响应中 `input_tokens` 不是 number，就返回 `null`；`/context` 随后调用 fallback，发 `messages.create(max_tokens=1, stream=false)` 做 token 估算。
- new-api 当前普通 Claude adaptor 的 `GetRequestURL()` 固定上游 `/v1/messages`，不能直接复用来处理 count_tokens，否则会把 token 计数请求错误地转成生成请求路径。
- 本任务 scope 是 `/root/project/new-api`。这是 cc2api count_tokens 兼容任务的下游补齐，不修改 cc2api。

## Clarifications

- Claude Code SDK 的正常 count_tokens 请求体不会带 `max_tokens`、`stream`、`temperature`、`top_p`、`top_k`、`stop_sequences` 这些生成专用字段；它们可能来自非 SDK 客户端、参数覆盖、或误把普通 messages 请求转给 count_tokens。实现应优先原样透传 SDK 合法字段，只在确定字段会污染 count_tokens 上游时做保守清理。
- `token-counting-2024-11-01` 不是随意添加的兼容项，而是 Anthropic TypeScript SDK 的 `beta.messages.countTokens()` 自动追加的 beta token。new-api 如果重建或覆盖 `anthropic-beta`，必须保证该 token 不丢失，否则上游可能按未启用 token counting beta 处理并导致失败。

## Requirements

- 新增 `POST /v1/messages/count_tokens` 路由，并复用 new-api 现有 relay 入口的认证、渠道选择、模型映射、渠道密钥和 header override 边界。
- count_tokens 必须走专用处理链路，不进入普通 Claude `/v1/messages` 生成请求的 `max_tokens` 默认补齐、流式响应处理、usage 结算、生成请求重试放大逻辑。
- 上游请求 URL 必须是 Claude 原生 `/v1/messages/count_tokens`；当客户端原请求带 `?beta=true` 或该渠道配置需要 beta query 时，上游 URL 必须保留 `beta=true`。
- 上游请求 header 必须包含 `anthropic-version`；缺失时按现有 Claude adaptor 规则默认 `2023-06-01`。
- 上游请求 header 必须保留原始 `anthropic-beta` 并确保包含 `token-counting-2024-11-01`，不能重复插入同一个 beta token。
- 请求体至少校验 `model` 非空、`messages` 存在且非空；支持 `tools`、`system`、`thinking` 等 Anthropic count_tokens 合法字段透传。
- 对生成专用字段采取保守策略：默认不要求 Claude Code 请求包含这些字段；如实现清理，只清理 count_tokens 不需要且可能导致上游拒绝的字段，并补测试说明。
- 上游成功响应按原始 JSON 透传给客户端，尤其必须保留 `input_tokens` number schema。
- 上游 4xx/5xx 错误按 Anthropic 风格返回给客户端，不伪造成成功；但不得在 count_tokens 路径内触发多渠道生成请求重试风暴。
- 不输出 Authorization、Cookie、token、完整 prompt、tool input、完整 request body 或完整 response body 到日志。

## Acceptance Criteria

- [ ] `POST /v1/messages/count_tokens?beta=true` 在 new-api 命中专用 handler，而不是 404 或普通 `/v1/messages` handler。
- [ ] new-api 转发到上游的路径是 `/v1/messages/count_tokens?beta=true`，不是 `/v1/messages`。
- [ ] 转发 header 中 `anthropic-beta` 包含 `token-counting-2024-11-01`，并保留客户端原有 beta token。
- [ ] 成功响应保留 `{"input_tokens": number}`，Claude Code 不再因响应 schema 不符触发 fallback。
- [ ] count_tokens 请求不被自动补 `max_tokens`，不进入普通 Claude usage 计费/结算路径。
- [ ] count_tokens 上游错误不会在同一客户端请求里按普通生成请求遍历多个渠道反复重试。
- [ ] 增加定向测试覆盖路由、header 注入、URL 构造、成功透传和错误透传。
- [ ] 在 `/root/project/new-api` 运行相关 Go 测试通过；如全量测试因环境或已有改动失败，记录失败原因并运行定向测试。

## Out of Scope

- 不实现本地 token 计算器。
- 不修改 Claude Code fallback 行为。
- 不修改 cc2api count_tokens 现有实现。
- 不处理 Vertex/Bedrock 专属 count_tokens 语义，除非 new-api 当前 Claude 渠道配置已明确需要。

## Research References

- `/root/project/new-api/router/relay-router.go`
- `/root/project/new-api/controller/relay.go`
- `/root/project/new-api/relay/helper/valid_request.go`
- `/root/project/new-api/relay/claude_handler.go`
- `/root/project/new-api/relay/channel/claude/adaptor.go`
- `/tmp/anthropic-sdk-0.39.0/package/src/resources/beta/messages/messages.ts`
- `/root/project/claude-code/src/services/tokenEstimation.ts`
