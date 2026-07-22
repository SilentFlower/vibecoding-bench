# Fable 被动配额研究

## 结论

- 可被动获取 Fable 独立周窗口，不必只依赖 `/api/oauth/usage`。
- 已验证的响应头窗口名为 `7d_oi`，对应 cc2api 的 `seven_day_fable`。
- 推荐解析 utilization、reset、status、surpassed-threshold，并把 Fable 耗尽作为模型级状态处理。
- Anthropic 官方公开文档未记录 `7d_oi`；实现必须允许头缺失并保留已有数据，不能用隐式主动查询兜底。
- 默认请求链路只做被动采集，不因响应头缺失自动调用 usage API。主动查询仅由账号显式开启的 `auto_poll_usage` 或管理员手动刷新触发。

## sub2api 最新实现

本地 `/root/project/sub2api` 已从 `f069c9ae0` fast-forward 到 `63cef6059`。

关键字段：

```text
anthropic-ratelimit-unified-7d_oi-utilization
anthropic-ratelimit-unified-7d_oi-reset
anthropic-ratelimit-unified-7d_oi-status
anthropic-ratelimit-unified-7d_oi-surpassed-threshold
anthropic-ratelimit-unified-representative-claim
```

关键实现：

- `backend/internal/service/ratelimit_service.go:1268-1335`：识别 Fable `7d_oi` 429，并设置模型级限流。
- `backend/internal/service/ratelimit_service.go:1685-1730`：从成功或错误响应头被动采集 5h/7d/7d_oi。
- `backend/internal/service/account_usage_service.go:183-190`：对外暴露 `seven_day_fable`。
- `backend/internal/service/account_usage_service.go:248-271`：主动 usage 字段 `seven_day_overage_included` 与 `7d_oi` 对应。
- `backend/internal/service/ratelimit_session_window_test.go:376-427`：Fable 被动采集及窗口重置清理测试。

## 对 cc2api 的启示

- cc2api 的 `extract_passive_usage` 应补充 `7d_oi -> seven_day_fable`。
- cc2api 的 429 路径当前用响应头做判断但不持久化，被动 Fable 采集需要覆盖该路径。
- sub2api 的“5h 窗口初始化时清空全部被动窗口”不能直接解决所有问题：清空后若同一响应头仍带旧高利用率，会立即重新写回。因此 cc2api 仍需要基于旧 reset 与新 reset 的跨周期合并规则。

## 联网核验

- Anthropic 官方 Claude Code 网关与配置文档没有公开 `7d_oi` 头的契约。
- Anthropic Claude Code 公共问题中可见 `anthropic-ratelimit-unified-*` 响应头用于消费窗口观测，但未形成稳定公开 API 文档。
- sub2api 公共仓库的提交 `b3f796972` 提供了当前最完整的 `7d_oi` 被动采集、模型级限流和测试证据。

参考：

- https://github.com/Wei-Shaw/sub2api
- https://github.com/Wei-Shaw/sub2api/commit/b3f796972e72536698c86ff87dd7d7155105e199
- https://github.com/anthropics/claude-code/issues/38335
- https://docs.anthropic.com/en/docs/claude-code/llm-gateway
