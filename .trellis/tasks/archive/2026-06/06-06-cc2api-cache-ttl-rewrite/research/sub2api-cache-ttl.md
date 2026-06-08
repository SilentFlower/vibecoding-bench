# sub2api cache_control TTL 行为参考

## 结论

sub2api 的 `forceEphemeralCacheControlTTL` 只改写已有 `cache_control.type == "ephemeral"` 的 `ttl`,不会新增新的 `cache_control` 对象,也不会新增缓存断点。

## 参考位置

- `/root/project/sub2api/backend/internal/service/gateway_service.go`
  - `injectAnthropicCacheControlTTL1h`
  - `forceEphemeralCacheControlTTL`
- `/root/project/sub2api/backend/internal/service/gateway_body_order_test.go`
  - `TestInjectAnthropicCacheControlTTL1h_OnlyUpdatesExistingEphemeralCacheControl`
- `/root/project/sub2api/backend/internal/service/gateway_tool_rewrite.go`
  - `applyToolsLastCacheBreakpoint`

## 范围对比

`forceEphemeralCacheControlTTL` 的扫描范围:

- 顶层 `cache_control`。
- `system[]` block。
- `messages[].content[]` block。
- `tools[]` tool。

`applyToolsLastCacheBreakpoint` 会在 tools 最后一个工具上新增 `cache_control`,属于另一个功能,本任务不仿照。
