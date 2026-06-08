# cc2api 访问策略错误体兼容 new-api

## Technical Design

### Scope

本任务只修改 `/root/project/cc2api` 中本地自定义拒绝响应的 JSON schema：

- `src/service/access_policy.rs` 的 `access_policy_error_response`
- `src/service/gateway.rs` 的 `system_role_model_error_response`

上游响应透传、account busy / 429 和通用 `AppError` 不在本任务内修改。

### Response Contract

访问策略拒绝时继续返回 HTTP 403，但响应体调整为 Anthropic / Claude 风格：

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "Claude Code 版本 '2.1.37' 不在允许范围内；允许范围：2.1.89-2.1.156"
  },
  "setting": "allowed_claude_code_versions",
  "reason": "Claude Code 版本 '2.1.37' 不在允许范围内；允许范围：2.1.89-2.1.156"
}
```

`setting` 和 `reason` 保留为 cc2api 自身诊断字段；new-api 会优先解析 `error` 对象中的 `message`。

system role 模型白名单拒绝继续返回 HTTP 400，但响应体调整为：

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "messages[].role=system is not allowed for this model",
    "code": "system_role_model_not_allowed"
  },
  "model": "claude-...",
  "allowed_system_role_models": ["..."]
}
```

### Compatibility

- new-api 的 `RelayErrorHandler` 会在 `error` 为对象时尝试解析 OpenAI 风格 `message/type/code` 字段。
- Claude 风格错误对象中的 `type/message` 已足够被 new-api 解析出 message。
- 顶层 `type: "error"` 保留 Anthropic 习惯，不影响 new-api 的 `GeneralErrorResponse` 解析。
- 上游返回的错误本身通常已经是 Anthropic 格式，继续原样透传，避免破坏 signature 降级判断和真实上游信息。
- `AppError::TooManyRequests("all accounts are busy")` 当前已能被 new-api 正常展示，不在本任务修改，避免影响重试/渠道状态逻辑。

### Risk

主要风险是已有客户端依赖旧的 `error` 字符串。本任务只覆盖 cc2api 本地自定义拒绝响应，并保留顶层诊断字段，优先保证代理链路可读性。

## Rollout / Rollback

- Rollout：修改两个本地拒绝响应函数，更新单测，重新构建镜像并重启 cc2api。
- Rollback：恢复两个响应函数旧 JSON schema。
