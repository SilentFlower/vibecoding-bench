# 修复 2.1.280 非遥测请求头与端点画像

## 需求来源与目标

用户已逐项要求修复上一轮解释的前三项，并让客户端决定 Sonnet 4.5 的 message-threads beta。目标是纠正原始抓包与 cc2api 实际发送之间已确认的差异。

## 范围

1. 原生 `/v1/messages` 透传 `x-claude-code-request-class` 与 `x-claude-code-prev-tool-durations`，不在其它端点注入。
2. 为 2.1.280 已观察的 Frame contract、MCP 子路径、model_selector 和组织插件/技能/marketplace 端点使用正确 UA、beta 和专用请求头；修正 mcp_servers capabilities。保持精确路径匹配及旧版本回滚。
3. 业务转发的 HTTP/1 请求按现有/补全的抓包画像发送大小写，保留代理、TLS、流式响应与重试。验证实际原始 TCP 字节。
4. 原生 Sonnet 4.5 messages 不再强制补 message-threads beta：有则保留，无则省略。API 生成模式保持默认画像，1M/Fast、safeguard、计数请求规则保持。

## 非目标

遥测、缓存环境正文、访问策略、TLS 指纹重构、生产部署、提交推送。

## 验收

- 两个 messages 新头和 Frame/MCP 专用头有端点正反例测试。
- 后台 UA/beta 按抓包匹配，近似路径与旧版本不误命中。
- Sonnet 4.5 有/无 beta 双分支及 API 默认回归通过。
- 本地 TCP 实测混合大小写、顺序、自动 Content-Length、重定向及代理请求；默认发送不受影响。
- cargo fmt --check、cargo test、cargo test cch 通过。

## Open Questions

无。Sonnet 条件采用用户选定的客户端权威策略，不猜测 feature flag。
