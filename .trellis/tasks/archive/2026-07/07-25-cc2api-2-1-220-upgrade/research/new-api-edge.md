# new-api hello 请求边界结论

## 拓扑

模型请求的标准调用链为：

```text
Claude Code -> ANTHROPIC_BASE_URL -> new-api -> cc2api
```

## 代码证据

- `new-api/router/relay-router.go` 的 `/v1` relay 先执行 `TokenAuth`、模型限流，再通过 `Distribute` 选择渠道。
- 本地运行 Claude Code 2.1.220 并把 `ANTHROPIC_BASE_URL` 指向脱敏探针时，探针收到 `POST /v1/messages?beta=true`，没有收到 `/api/hello`。
- 原始抓包确认 hello 实际为 `HEAD https://api.anthropic.com/api/hello`，User-Agent 为 `Bun/1.4.0`，响应状态为 200、`Content-Length: 20`。
- hello 当前不使用 `ANTHROPIC_BASE_URL`，因此不会进入 new-api，也没有可供 new-api 执行渠道选择的请求。

## 设计结论

- 当前不修改 new-api 路由、渠道分发或全局配置。
- cc2api 保留 `GET/HEAD /api/hello`，支持直接访问和内部健康检查场景。
- 不新增无鉴权渠道选择、硬编码 cc2api 渠道或通用代理旁路。
- 后续只有客户端开始让 hello 使用 `ANTHROPIC_BASE_URL` 时，才重新抓包并评估透传或本地响应策略。

## Linked Task

- `/root/project/new-api/.trellis/tasks/07-25-claude-code-api-hello`
