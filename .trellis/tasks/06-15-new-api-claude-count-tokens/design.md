# new-api 支持 Claude count_tokens 透传 - 设计

## Technical Design

### 边界

`/v1/messages/count_tokens` 是 Claude 原生 token counting API，不是生成请求。new-api 需要给它专用入口，避免进入普通 `Relay()` 中的生成请求预扣费、usage 结算、`max_tokens` 默认补齐和重试逻辑。

### 推荐链路

1. Router 增加 `POST /v1/messages/count_tokens`。
2. 入口复用现有中间件顺序：`RouteTag("relay")`、`SystemPerformanceCheck()`、`TokenAuth()`、`ModelRequestRateLimit()`、`Distribute()`。
3. Controller 新增 `RelayClaudeCountTokens(c)` 或等价专用函数。
4. Handler 读取 reusable body，校验 JSON object、`model`、`messages`。
5. 使用已经分配到 Gin context 的渠道信息构造 `RelayInfo` 或轻量上下文，拿到 channel base URL、api key、渠道设置、header override。
6. 上游 URL 使用 `${base}/v1/messages/count_tokens`，根据客户端 query 或渠道配置追加 `beta=true`。
7. Header 复用 Claude adaptor 的认证和 Anthropic header 写入规则，并在写入后合并 `token-counting-2024-11-01`。
8. HTTP 响应按上游 status/body/header 透传，过滤 hop-by-hop header。

### 请求体策略

Claude Code SDK 正常 body 形态是：

```json
{
  "model": "...",
  "messages": [...],
  "tools": [...],
  "thinking": {"type": "enabled", "budget_tokens": 1024}
}
```

SDK 会把 `betas` 从 body 剥离到 `anthropic-beta` header。实现不应为了“兼容”而把正常字段改坏。

生成专用字段清理只作为防御：如果请求体中出现 `max_tokens`、`stream`、`temperature`、`top_p`、`top_k`、`stop_sequences`、`stop`，可以从上游 count_tokens body 中移除，因为这些是生成请求参数，不参与 token counting，并且可能被 Anthropic count_tokens 拒绝。测试要覆盖“清理后仍保留 model/messages/tools/thinking/system”。

### Beta Header

Anthropic TypeScript SDK 0.39.0 的 `beta.messages.countTokens()` 明确追加：

```ts
'anthropic-beta': [...(betas ?? []), 'token-counting-2024-11-01'].toString()
```

new-api 在代理时如果重建 header，就必须保证该 token 存在。合并逻辑应去重并保留原有顺序的大体稳定性。

抓包 `/root/project/vibecoding-bench/data/flows/6-5/3338/1b19b983b62f` 显示，真实 `count_tokens` 请求的 `anthropic-beta` 是 SDK 为计数接口准备的专用集合，例如包含 `claude-code-20250219`、`oauth-2025-04-20`、`interleaved-thinking-2025-05-14`、`context-management-2025-06-27`、`token-counting-2024-11-01`；它不等同于普通 `/v1/messages` 生成请求的模型级 beta 集合。因此 count_tokens 专用链路不应调用 `GetClaudeSettings().WriteHeaders` 混入普通 messages 的模型级 header，应该以客户端原始 header 为主，再应用渠道 header override，并兜底补齐 `token-counting-2024-11-01`。

### 计费和重试

count_tokens 是辅助计数接口，不产生模型输出，不应按普通生成请求结算 usage。可以保留 token 级别的本地鉴权、余额检查或轻量限流，但不应执行普通生成请求的预扣最大输出 token 逻辑。

上游错误应直接返回给客户端。特别是 429/529 不应按普通生成请求跨渠道多次重试，否则会再次放大 Claude Code `/context` 的并发计数请求。

## Rollout / Rollback

上线后用 Claude Code `/context` 经过 new-api 复测：

- 预期 new-api 日志出现 count_tokens 专用请求。
- cc2api 下游日志出现 `count_tokens_forward`。
- 同一时间不再出现大量 `max_tokens=1` 非流 fallback。

如上线后出现异常，回滚 new-api 镜像即可；cc2api 直连路径不受影响。
