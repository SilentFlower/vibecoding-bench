# cc2api Claude Code 2.1.156 传输层与 Header Wire 指纹优化

## Goal

基于真实 Claude Code `2.1.156` 抓包，对 cc2api 的出站 header wire 形态和传输层行为做对比与优化，减少“header 值正确但 wire 行为不像真实 Bun/native HTTP 客户端”的差异。

## Background / Known Context

- 抓包目录：`/root/project/vibecoding-bench/data/flows/auto-2/1887/46ba25a8d791/`。
- 安全摘要显示该 run 共 60 条 flow，host 全部为 `api.anthropic.com`。
- 本次抓包未捕获到 Datadog host 或 WebSocket upgrade。
- 父任务已按 endpoint 升级 header profile，包括 `/v1/messages`、`/api/event_logging/v2/batch`、`/api/eval/*`、OAuth、triggers、MCP。
- 目前 cc2api 出站仍由 Rust HTTP client / tlsfp 负责，不是真实 Claude Code 的 Bun/native HTTP 栈。
- 风险点包括 header 顺序、header 大小写、accept-encoding、HTTP 版本、连接复用、TLS ClientHello、超时和重试节奏、body 序列化后字段顺序。

## Requirements

- 从 `http_capture.jsonl` 和 `.flow` 中提取安全 wire 摘要：endpoint、method、header 顺序、header 大小写、重复 header、HTTP 版本、content encoding、连接复用线索、状态码、时间间隔。
- 建立 cc2api 本地对比抓包方法：用 dummy upstream 或本地 mitm 捕获 cc2api 生成的同类请求，输出同样的 wire 摘要。
- 形成真实 Claude Code vs cc2api 的差异表，区分：
  - 已确认差异。
  - 抓包样本不足，暂不改。
  - 不适合在 cc2api 中模拟的传输层差异。
- 对已确认且低风险的差异进行优化，例如 header casing/order、per-endpoint accept-encoding、连接复用策略、timeout/retry header。
- 不盲目伪装 `Bun/1.3.14` 底层传输；只有抓包对比证明差异可控时才改 tlsfp/client profile。
- 保持 endpoint profile 可维护，避免把 wire 特例散落在 gateway、oauth、telemetry 多处。

## Acceptance Criteria

- [ ] 有一份安全 wire 指纹摘要，覆盖 `46ba25a8d791` 中主要 endpoint 的 header order/casing/encoding/HTTP 行为。
- [ ] 有一份 cc2api 本地对比摘要，使用同一格式输出。
- [ ] 有差异表和决策记录，说明哪些差异修、哪些暂不修、哪些不能修。
- [ ] 已确认的 header wire 差异有测试覆盖，至少包括 `/v1/messages`、`/api/event_logging/v2/batch`、`/api/eval/*`、`/v1/mcp_servers`、`/v1/code/triggers`。
- [ ] 不引入 token、prompt、响应体全文或抓包原文到 git。
- [ ] README 或任务研究记录说明传输层兼容范围和剩余风险。

## Out of Scope

- 不承诺完全复刻 Bun/native HTTP 的 TLS/HTTP 栈。
- 不在样本不足时实现 Datadog/WebSocket 模拟；当前 run 未捕获相关流量。
- 不处理账号运营策略、封禁规避策略或平台风控绕过策略。

## Research References

- 抓包目录：`data/flows/auto-2/1887/46ba25a8d791/`
- 父任务：`.trellis/tasks/06-04-cc2api-claude-code-2156-cch-upgrade`
- 目标代码：`/root/project/cc2api/src/service/rewriter.rs`、`/root/project/cc2api/src/tlsfp.rs`、`/root/project/cc2api/src/service/oauth.rs`、`/root/project/cc2api/src/service/telemetry.rs`
