# cc2api Wire Profile 对比摘要

## 生成方式

本摘要基于 cc2api 当前代码中的 endpoint header profile：

- `/root/project/cc2api/src/service/rewriter.rs`
  - `Rewriter::rewrite_headers`
  - `ordered_anthropic_headers`
- `/root/project/cc2api/src/service/gateway.rs`
  - `forward_request` 统一按 `ordered_anthropic_headers` 添加 header
- `/root/project/cc2api/src/service/telemetry.rs`
  - `send_telemetry` 先补齐自动遥测 endpoint header profile，再统一按 `ordered_anthropic_headers` 添加 header
- `/root/project/cc2api/src/service/prime_poller.rs`
  - 预热 `/v1/messages` 请求统一按 `ordered_anthropic_headers` 添加 header

这是代码侧 expected wire profile，不包含 Authorization 值、body 原文或响应体原文。

## 修复后 endpoint profile

| endpoint | cc2api header order |
|---|---|
| `/v1/messages` | `Accept`, `Authorization`, `Content-Type`, `User-Agent`, `X-Claude-Code-Session-Id`, `X-Stainless-Arch`, `X-Stainless-Lang`, `X-Stainless-OS`, `X-Stainless-Package-Version`, `X-Stainless-Retry-Count`, `X-Stainless-Runtime`, `X-Stainless-Runtime-Version`, `X-Stainless-Timeout`, `anthropic-beta`, `anthropic-dangerous-direct-browser-access`, `anthropic-version`, `x-app`, `x-client-request-id`, `Connection`, `Host`, `Accept-Encoding` |
| `/api/event_logging/v2/batch` | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `x-service-name`, `Connection`, `Host` |
| `/api/eval/sdk-zAZezfDKGoZuXXKe` | `Authorization`, `Content-Type`, `anthropic-beta`, `Connection`, `User-Agent`, `Accept`, `Host`, `Accept-Encoding` |
| `/v1/code/triggers` | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `anthropic-client-platform`, `anthropic-version`, `x-organization-uuid`, `Connection`, `Host` |
| `/v1/mcp_servers` | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `anthropic-version`, `Connection`, `Host` |
| `/mcp-registry/v0/servers` | `Accept`, `Accept-Encoding`, `User-Agent`, `Connection`, `Host` |
| `/api/oauth/account/settings` | `Accept`, `Accept-Encoding`, `Authorization`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |
| `/api/claude_code_grove` | `Accept`, `Accept-Encoding`, `Authorization`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |
| `/api/claude_code_penguin_mode` | `Accept`, `Accept-Encoding`, `Authorization`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |

`Content-Length` 由 reqwest/hyper 根据 body 自动追加，未在应用层 profile 中手工插入。

## Diff 结论

| 项 | 真实抓包 | cc2api 修复后 | 结论 |
|---|---|---|---|
| `/v1/messages` header order | 21 个应用层 header + `Content-Length` | 21 个应用层 header；`Content-Length` 自动追加 | 已对齐应用层顺序 |
| `/api/event_logging/v2/batch` header order | 9 个应用层 header + `Content-Length` | 9 个应用层 header；`Content-Length` 自动追加 | 已对齐应用层顺序 |
| `/api/eval/*` header order | 8 个应用层 header + `Content-Length` | 8 个应用层 header；`Content-Length` 自动追加 | 已对齐应用层顺序 |
| `/v1/mcp_servers` / `/v1/code/triggers` | GET 带 `Content-Type` | 保留 `Content-Type` | 已对齐 |
| OAuth/grove/penguin/registry GET | 不带 `Content-Type` | 不再主动加 `Content-Type` | 已修复 |
| 自动 event logging / eval | 带 endpoint 专属 `Accept` / `Accept-Encoding` 并保持稳定顺序 | `telemetry_request_headers` 补齐后排序发送 | 已修复 |
| 预热 `/v1/messages` | 与主 `/v1/messages` wire profile 一致 | `prime_poller` 复用统一排序 helper | 已修复 |
| `HEAD /` 404 探测 | 单条样本：`Connection`, `User-Agent`, `Accept`, `Host`, `Accept-Encoding` | 未模拟 | 暂不修：根路径探测不属于当前主要 API 转发/自动遥测链路 |
| HTTP version | HTTP/1.1 | `tlsfp` ALPN 只声明 `http/1.1` | 保持 |
| TLS/Bun native transport | 未做 ClientHello 对比 | 未修改 | 暂不改 |

## 测试覆盖

新增/更新的测试：

- `service::rewriter::tests::endpoint_wire_order_matches_2156_capture`
- `service::rewriter::tests::get_profile_omits_content_type_when_capture_has_none`
- `service::telemetry::tests::telemetry_headers_match_2156_wire_profile`
- 既有 `endpoint_headers_use_distinct_profiles` 继续覆盖 endpoint header 值 profile。
