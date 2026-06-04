# Claude Code 2.1.156 Wire 指纹分析

## 输入边界

来源为 `data/flows/auto-2/1887/46ba25a8d791/20260604-024430.flow` 和 `http_capture.jsonl` 的结构化解析结果。本分析只记录 endpoint、method、HTTP version、status、header 名顺序、少量安全 header 枚举值、body 长度范围；不记录 Authorization 值、cookie、请求体全文、响应体全文、token、prompt 或 `.flow` 原文。

安全摘要脚本：`research/wire_summary.py`。

## 真实抓包摘要

本轮只分析 `api.anthropic.com`。`.flow` 中另有 DNS、Datadog、npm registry、raw GitHub 等流量；PRD 目标 endpoint 以 Anthropic API 为主。复核时重新从 `.flow` 生成安全摘要，实际包含 61 条 `api.anthropic.com` flow，其中 60 条是主要 Anthropic API endpoint，另有 1 条 `HEAD /` 404 探测样本。

| endpoint | count | method | HTTP | status | header order |
|---|---:|---|---|---|---|
| `/api/event_logging/v2/batch` | 32 | POST | HTTP/1.1 | 31x 200, 1x no response | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `x-service-name`, `Connection`, `Host`, `Content-Length` |
| `/v1/messages` | 17 | POST | HTTP/1.1 | 17x 200 | `Accept`, `Authorization`, `Content-Type`, `User-Agent`, `X-Claude-Code-Session-Id`, `X-Stainless-Arch`, `X-Stainless-Lang`, `X-Stainless-OS`, `X-Stainless-Package-Version`, `X-Stainless-Retry-Count`, `X-Stainless-Runtime`, `X-Stainless-Runtime-Version`, `X-Stainless-Timeout`, `anthropic-beta`, `anthropic-dangerous-direct-browser-access`, `anthropic-version`, `x-app`, `x-client-request-id`, `Connection`, `Host`, `Accept-Encoding`, `Content-Length` |
| `/mcp-registry/v0/servers` | 4 | GET | HTTP/1.1 | 4x 200 | `Accept`, `Accept-Encoding`, `User-Agent`, `Connection`, `Host` |
| `/` | 1 | HEAD | HTTP/1.1 | 404 | `Connection`, `User-Agent`, `Accept`, `Host`, `Accept-Encoding` |
| `/api/eval/sdk-zAZezfDKGoZuXXKe` | 1 | POST | HTTP/1.1 | 200 | `Authorization`, `Content-Type`, `anthropic-beta`, `Connection`, `User-Agent`, `Accept`, `Host`, `Accept-Encoding`, `Content-Length` |
| `/api/oauth/account/settings` | 1 | GET | HTTP/1.1 | 200 | `Accept`, `Accept-Encoding`, `Authorization`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |
| `/api/claude_code_grove` | 1 | GET | HTTP/1.1 | 200 | `Accept`, `Accept-Encoding`, `Authorization`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |
| `/api/claude_code_penguin_mode` | 1 | GET | HTTP/1.1 | 200 | `Accept`, `Accept-Encoding`, `Authorization`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |
| `/api/claude_cli/bootstrap` | 1 | GET | HTTP/1.1 | 200 | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `Connection`, `Host` |
| `/v1/mcp_servers` | 1 | GET | HTTP/1.1 | 200 | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `anthropic-version`, `Connection`, `Host` |
| `/v1/code/triggers` | 1 | GET | HTTP/1.1 | 200 | `Accept`, `Accept-Encoding`, `Authorization`, `Content-Type`, `User-Agent`, `anthropic-beta`, `anthropic-client-platform`, `anthropic-version`, `x-organization-uuid`, `Connection`, `Host` |

主要安全 header 值：

| endpoint | Accept | Accept-Encoding | User-Agent | anthropic-beta |
|---|---|---|---|---|
| `/v1/messages` | `application/json` | `gzip, deflate, br, zstd` | `claude-cli/2.1.156 (external, cli)` | 多组 beta；主样本含 `claude-code-20250219`、`context-1m-2025-08-07`、`mid-conversation-system-2026-04-07` 等 |
| `/api/event_logging/v2/batch` | `application/json, text/plain, */*` | `gzip, compress, deflate, br` | `claude-code/2.1.156` | `oauth-2025-04-20` |
| `/api/eval/sdk-zAZezfDKGoZuXXKe` | `*/*` | `gzip, deflate, br, zstd` | `Bun/1.3.14` | `oauth-2025-04-20` |
| `/v1/mcp_servers` | `application/json, text/plain, */*` | `gzip, compress, deflate, br` | `axios/1.15.2` | `mcp-servers-2025-12-04` |
| `/v1/code/triggers` | `application/json, text/plain, */*` | `gzip, compress, deflate, br` | `claude-cli/2.1.156 (external, cli)` | `ccr-triggers-2026-01-30` |

## cc2api 对比摘要

代码侧对比基于 `Rewriter::rewrite_headers`、`ordered_anthropic_headers` 和 `tlsfp::make_request_client`：

- `tlsfp` 当前 ALPN 只声明 `http/1.1`，与本次 Anthropic API 抓包一致。
- header 值 profile 已覆盖主要 endpoint：messages、event logging、eval、OAuth、bootstrap、triggers、MCP、registry。
- 修复前 gateway 用 `HashMap` 遍历 header，wire 插入顺序不稳定；修复后统一通过 `ordered_anthropic_headers` 按 endpoint 顺序添加。
- 修复前 API 模式会给部分 GET 配置类 endpoint 无条件加 `content-type: application/json`；真实抓包中 `/api/oauth/account/settings`、`/api/claude_code_grove`、`/api/claude_code_penguin_mode`、`/mcp-registry/v0/servers` 不带 content-type；修复后这些 endpoint 不再主动加 content-type。
- 自动遥测 `send_telemetry` 修复前不走 gateway header ordering，且缺少真实抓包中的 `Accept` / `Accept-Encoding` endpoint 默认值；修复后 event logging 和 GrowthBook eval 会先构造 2.1.156 endpoint header profile，再复用 `ordered_anthropic_headers`。
- 预热请求 `prime_poller` 修复前仍遍历 `HashMap` 并手工补 Host；修复后 `/v1/messages` 预热链路也复用 `ordered_anthropic_headers`。

## 差异表与决策

| 差异 | 证据 | 决策 |
|---|---|---|
| header order 不稳定 | cc2api gateway 与预热链路使用 `HashMap` 遍历；真实抓包主要 endpoint order 稳定 | 已修：新增 `ordered_anthropic_headers` 并在 gateway/telemetry/prime_poller 复用 |
| 自动遥测 header 集合不完整 | `send_telemetry` 原先只显式发送 Content-Type、User-Agent、beta、Authorization、x-service-name；真实 event logging / eval 还带 endpoint 专属 Accept 与 Accept-Encoding | 已修：自动 event logging / GrowthBook eval 补齐 endpoint header profile 后再排序发送 |
| GET 配置类 endpoint 多余 content-type | 真实抓包 OAuth/grove/penguin/registry GET 无 content-type | 已修：`requires_json_content_type` 排除这些 endpoint |
| `/v1/messages` beta 集合可能仍少于主样本 | 真实主样本含更多 beta；父任务目前采用保守 beta 集合，并有 1M 白名单策略 | 暂不修：beta 策略涉及计费/功能开关，需单独评估 |
| TLS ClientHello / Bun native HTTP 栈 | 本轮证据只确认 HTTP/1.1；无 TLS 指纹对比数据 | 暂不修：不凭猜测改 `tlsfp.rs` |
| Datadog / WebSocket | 本次 `http_capture.jsonl` 未捕获目标 host 或 WS upgrade；`.flow` 虽有 Datadog logs，但不在 cc2api 当前出站 API 主链路 | 暂不修：样本不足且超出当前 endpoint profile |
| `HEAD /` 404 探测样本 | 复核 `.flow` 发现 1 条 `HEAD /`，header 顺序为 `Connection`, `User-Agent`, `Accept`, `Host`, `Accept-Encoding`，UA 为 `Bun/1.3.14` | 暂不修：它是单条根路径探测/健康类流量，不属于 cc2api 当前主要 API 转发或自动遥测链路；若后续要模拟启动探测，单独建任务处理 |
| body JSON 字段顺序 | 抓包有 body 长度范围，但本分析不输出 body 原文；cc2api 使用 serde_json 重新序列化 | 暂不修：需要专门 body schema 对比，不纳入本轮低风险 header 修复 |

## 剩余风险

- reqwest/hyper 是否完全保留 header 大小写和最终 Content-Length 位置仍取决于底层实现；本轮修复保证应用层插入顺序稳定。
- Connection/Host 由 helper 显式补齐，但最终 wire 仍可能被 HTTP client 调整。
- 本轮未改变 TLS 指纹，不承诺完全复刻 Bun/native HTTP 栈。
