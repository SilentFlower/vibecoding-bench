# 强化 cc2api count_tokens 兼容

## Goal

在 `/root/project/cc2api` 中补齐 Claude 原生 `POST /v1/messages/count_tokens` 的专用处理链路，参考 `sub2api` 的成熟行为，避免 Claude Code `/context` 做上下文 token 分析时退化成大量 `max_tokens=1` 的 Opus 非流 `/v1/messages` 探针请求，从而触发上游 429 风暴。

## Background / Known Context

- 用户在远程 `cc2api` 复现：使用 Claude Code `/context` 后出现 429。
- 远程 `vibecoding-bench` 抓包 run `data/flows/6-5/3338/1b19b983b62f` 显示，直连 Anthropic 时 `/context` 之后的主请求是 `POST /v1/messages?beta=true`，`model=claude-opus-4-8`，`stream=true`，`max_tokens=64000`，并命中 `Context management` / `Session-specific guidance`。
- 远程 `cc2api` 容器日志显示 429 形态不是主流式请求，而是同一时间出现大量 `POST /v1/messages`、`model=claude-opus-4-8`、`max_tokens=1`、`message_count=1` 的非流请求，上游返回 `rate_limit_error`。聚合样本中 184 条 429 均为该形态，并被 cc2api 的换号重试放大到多个账号。
- Claude Code 的 `/context` 是本地 slash command。其 token 统计优先应走 Anthropic `messages.countTokens`；失败时会 fallback 到 `messages.create(max_tokens=1)`，这是当前 429 风暴的直接诱因。
- `cc2api` 当前通过 router fallback 处理所有网关路径，`/v1/messages/count_tokens` 没有专用分支，因此会进入普通 Gateway 热路径：账号选择、RPM、并发槽、body/header rewrite、非流探针日志、429 换号重试等。
- `sub2api` 已有专用 `POST /v1/messages/count_tokens` 路由和 `ForwardCountTokens` 链路。其关键行为是：校验认证/余额、选择账号、转发 count_tokens、不记录 usage、不走普通 messages 并发和使用量计费路径、为 count_tokens 补齐 `token-counting-2024-11-01` beta。

## Requirements

- 新增或强化 `cc2api` 对 `POST /v1/messages/count_tokens` 的专用处理，不能让该接口继续被普通 `/v1/messages` 热路径隐式处理。
- 专用链路必须复用现有 API token 鉴权、账号允许/禁止列表、账号模型支持、OAuth token 解析、代理/TLS 指纹和上游错误格式边界。
- count_tokens 请求必须以非流 JSON 请求转发到 Anthropic 上游 `/v1/messages/count_tokens?beta=true`，成功响应按 Anthropic JSON 原样返回给客户端。
- count_tokens 链路不应消耗普通 `/v1/messages` 的本地 RPM 名额，不应占用账号并发槽，不应触发非流探针缓存/日志，不应记录 message usage，不应触发 telemetry message request。
- OAuth / Claude Code 请求必须确保 `anthropic-beta` 最终包含 `token-counting-2024-11-01`；缺失时补齐，同时保留 cc2api 已有 Claude Code 必需 beta 顺序约束。
- 请求体处理至少覆盖：
  - 读取 body 后可转发最终 body，不出现空 body。
  - 解析 `model` 必填。
  - 对账号模型映射/模型规范化的处理与 `/v1/messages` 现有规则保持一致或在设计中明确差异。
  - 清理空 text block 等低风险兼容处理可参考 sub2api，但不能引入完整提示内容日志。
- 上游 404/不支持 count_tokens 的情况应返回 Anthropic 风格 404，让 Claude Code 退回本地估算或自身 fallback；不要把不支持路径伪装成成功。
- 上游 429/529 等错误应返回 Anthropic 风格错误；count_tokens 的 429 不应被普通消息换号重试成风暴。是否对账号限流状态做轻量标记需要在设计中明确，默认不进行跨账号重复重试。
- 所有新增日志必须脱敏，不输出 Authorization、Cookie、token、完整 prompt、tool input、完整 request body 或完整 response body。
- 需要补充定向测试，覆盖路由分流、beta 注入、成功透传、错误透传、避免普通非流探针路径、避免普通 429 换号风暴。

## Acceptance Criteria

- [ ] `POST /v1/messages/count_tokens` 命中专用 handler/service，不进入普通 `/v1/messages` 的非流探针日志、缓存和 telemetry 逻辑。
- [ ] 上游请求 URL 为 `/v1/messages/count_tokens?beta=true`，而不是 `/v1/messages`。
- [ ] OAuth/Claude Code count_tokens 上游 header 含 `token-counting-2024-11-01`，且 Authorization 使用选中账号的上游 token。
- [ ] 成功响应以 `application/json` 返回，并保留上游 `input_tokens` schema。
- [ ] count_tokens 上游 429 只向客户端返回一次合理错误，不在同一请求内遍历多个账号反复打同类请求。
- [ ] `/context` 场景下 Claude Code 不再因 count_tokens 未处理而产生大批 Opus `max_tokens=1` 非流 fallback 请求。
- [ ] `cd cc2api && cargo fmt --check` 通过。
- [ ] `cd cc2api && cargo test` 通过；如全量测试因环境问题失败，需记录失败原因并至少运行相关定向测试。

## Out of Scope

- 不实现本地 token 精确计算器。
- 不重写 Claude Code `/context` 本地命令行为。
- 不引入新的管理页设置，除非实现过程中发现必须提供兼容开关。
- 不提交完整抓包、prompt、token、Authorization、Cookie 或账号敏感映射。

## Research References

- `sub2api`: `/root/project/sub2api/backend/internal/server/routes/gateway.go`
- `sub2api`: `/root/project/sub2api/backend/internal/handler/gateway_handler.go`
- `sub2api`: `/root/project/sub2api/backend/internal/service/gateway_service.go`
- `sub2api`: `/root/project/sub2api/backend/internal/pkg/claude/constants.go`
- `cc2api`: `/root/project/cc2api/src/handler/router.rs`
- `cc2api`: `/root/project/cc2api/src/service/gateway.rs`
- 远程排查摘要：`/context` 触发的 cc2api 429 来源为 Opus `max_tokens=1` 非流 fallback 风暴，而非主流式请求。
