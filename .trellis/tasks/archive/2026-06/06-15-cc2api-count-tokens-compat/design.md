# 强化 cc2api count_tokens 兼容 - 设计

## Technical Design

### 边界

目标代码仓库是 `/root/project/cc2api`。当前 `vibecoding-bench` 只保存 Trellis 任务记录和排查结论。

新增能力聚焦 Anthropic 原生：

```text
POST /v1/messages/count_tokens
```

该路径必须从普通 gateway fallback 热路径中分离，避免进入 `/v1/messages` 的非流探针、RPM、并发槽、telemetry 和 429 换号重试逻辑。

### 路由与 handler

在 `cc2api/src/handler/router.rs` 中为 `/v1/messages/count_tokens` 增加显式 POST 路由。该路由仍使用现有 `extract_key` / `TokenStore` 鉴权，鉴权通过后调用 `GatewayService` 的 count_tokens 专用方法。

保持现有 fallback 处理其他路径：

```text
/v1/messages                  -> 现有 GatewayService::handle_request
/v1/messages/count_tokens     -> 新 count_tokens 专用入口
其他 Anthropic/Claude Code 路径 -> 现有 fallback
```

### Service 流程

新增 `GatewayService::handle_count_tokens_request` 或等价方法，建议流程：

1. 记录 method/path/query/header 元数据，不记录完整 body。
2. 读取 body，大小上限沿用现有 gateway body 限制。
3. 解析 JSON，校验 `model` 必填。
4. 识别客户端类型，生成与现有 messages 兼容的 session hash。
5. 应用 API token 的 allowed/blocked account ids。
6. 选择账号，但不进入普通 RPM admission，也不占用并发槽。
7. 进行 count_tokens 专用 body/header 处理。
8. 获取账号上游 token。
9. 转发到 `/v1/messages/count_tokens?beta=true`。
10. 成功响应原样返回 JSON；错误响应转换为 Anthropic 风格错误并保持状态码。

默认不在同一 count_tokens 请求内对 429 做跨账号重试。原因是 `/context` 会并发触发多项 token 统计，跨账号重试会把一个客户端 fallback 放大成多账号上游风暴。

### Header / beta

count_tokens 与 messages 的关键差异是必须包含 token counting beta：

```text
token-counting-2024-11-01
```

实现时应复用现有 header rewrite 能力或抽出小函数：

- 保留 `anthropic-version`、`User-Agent`、`x-app` 等现有 Claude Code profile 逻辑。
- 最终 `anthropic-beta` 必须包含 `token-counting-2024-11-01`。
- 如果客户端已有 `anthropic-beta`，在保留允许 beta 的基础上补齐 token-counting。
- 如果客户端没有 `anthropic-beta`，OAuth/Claude Code 请求使用包含 `claude-code-20250219`、`oauth-2025-04-20`、`interleaved-thinking-2025-05-14`、`token-counting-2024-11-01` 的最小 count_tokens beta 集合。
- 不能把 `context-1m-2025-08-07` 无条件加入 count_tokens；保留现有 1M 白名单/客户端 beta 语义。

### Body / model

count_tokens body schema 与 `/v1/messages` 接近，但没有 `max_tokens` 必需语义。处理策略：

- 不注入 `max_tokens=1`。
- 不把 count_tokens 改写成 `/v1/messages`。
- 对模型短名、账号模型映射、Fable/Opus 等行为尽量复用现有 rewriter 或模型 helper。
- 可增加 `StripEmptyTextBlocks` 等小范围兼容处理，避免上游 400；但必须保持 JSON 结构，不做完整 prompt 级重构。
- 如果复用 `rewrite_body_with_stateful_completion`，必须确认不会写入 stateful cache 锚点、不会触发 CCH/cc_version 只适用于 messages 的副作用。更保守的方案是为 count_tokens 提供独立轻量 body rewrite。

### 错误处理

返回 Anthropic 风格：

```json
{
  "type": "error",
  "error": {
    "type": "<error_type>",
    "message": "<message>"
  }
}
```

建议规则：

- 本地鉴权失败沿用现有网关错误。
- body 为空/JSON 无效/model 缺失返回 `400 invalid_request_error`。
- 无可用账号返回 `503 api_error` 或沿用现有 `AppError::ServiceUnavailable` 对应格式。
- 上游 404 且明显是不支持 count_tokens：返回 `404 not_found_error`，让客户端自行 fallback。
- 上游 429：返回 `429 upstream_error` 或保留上游 `rate_limit_error`，但不在同一请求内遍历所有账号。
- 上游 529：返回 `529 upstream_error` 或对应现有错误结构。

### 日志与隐私

新增日志只记录：

- path
- account id/name
- model
- request body byte length/hash
- status
- upstream request id

禁止记录完整 prompt、tool input、Authorization、Cookie、access_token、refresh_token、完整响应体。

### 与 sub2api 的取舍

直接参考 sub2api 的完整思想，但不机械搬运：

- 搬：专用路由、专用 ForwardCountTokens、token-counting beta、成功透传、错误降级、404 fallback 语义。
- 不搬：sub2api 的 group platform、billing cache、ops metrics、Antigravity 分支、复杂 OpenAI 平台隔离。
- 延后：API-key passthrough 的全量 header 复制细节，可按 cc2api 现有账号类型和 token 获取方式实现最小等价。

## Rollout / Rollback

- 本地先以单元测试和定向 cargo test 验证。
- 远程部署前开启 429/non-stream 脱敏观测即可，不需要新增永久 setting。
- 部署后用 Claude Code `/context` 验证：
  - cc2api 日志出现 `/v1/messages/count_tokens`；
  - 不再出现同一 `/context` 批量 Opus `max_tokens=1` 非流 429；
  - 主 `/v1/messages` 流式请求仍可正常返回。
- 回滚方式：回退 cc2api 代码/镜像到上一版本。该任务不需要 DB migration，回滚不涉及数据修复。
