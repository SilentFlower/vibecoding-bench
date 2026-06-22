# Claude Code 2.1.185 抓包摘要（脱敏）

## Source

- 本地抓包目录：`data/flows/6-5/3930/dac88465b061/`
- 只记录协议字段摘要，不记录完整 prompt、响应正文、token、Cookie、Authorization 或邮箱。

## Endpoint Counts

- `POST /v1/messages?beta=true`：13 条
- `POST /api/event_logging/v2/batch`：52 条
- `POST /api/eval/sdk-zAZezfDKGoZuXXKe`：1 条
- `GET /api/oauth/account/settings`：1 条
- `GET /api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8`：1 条
- `GET /api/claude_code_grove`：1 条
- `GET /api/claude_code_penguin_mode`：1 条
- `GET /v1/code/triggers`：1 条
- `GET /v1/mcp_servers?limit=1000`：1 条
- `GET /mcp-registry/v0/servers...`：4 条
- `HEAD /`：1 条

## Version Profile

- CLI UA：`claude-cli/2.1.185 (external, cli)`
- Code UA：`claude-code/2.1.185`
- `env.version=2.1.185`
- `env.version_base=2.1.185`
- `env.build_time=2026-06-20T06:38:30Z`
- `env.node_version=v24.3.0`
- `X-Stainless-Package-Version=0.94.0`
- `X-Stainless-Runtime=node`
- `X-Stainless-Runtime-Version=v24.3.0`
- GrowthBook eval / `HEAD /` UA：`Bun/1.4.0`

## `/v1/messages` Header / Body

- 主请求模型：`claude-opus-4-8`
- 主请求 `max_tokens=64000`
- 主请求 `thinking={"type":"adaptive"}`
- 主请求 body 顶层字段包含：`model`、`messages`、`system`、`tools`、`metadata`、`max_tokens`、`thinking`、`context_management`、`output_config`、`diagnostics`、`stream`
- 主请求 beta：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

## `cc_version`

- Haiku 辅助请求样本：`cc_version=2.1.185.d1d`
- Opus 主请求样本：`cc_version=2.1.185.530`
- 13 条 messages 中 12 条带 billing header，12/12 命中既有后缀算法。
- 主请求首条 user message 有 2 个 text block，后缀文本源仍取最后一个 text block。

## CCH

- 12 条 billing 请求全部命中既有 `2.1.172` / `2.1.173` 归一化算法：
  - seed：`0x4D659218E32A3268`
  - 先将真实 `cch=<5hex>` 替回 `cch=00000`
  - 顶层 `model` 值替换为 `""`
  - 删除顶层 `max_tokens`
  - 删除顶层 `fallbacks`
  - `xxhash64(input, seed) & 0xFFFFF`

## Telemetry

- `POST /api/event_logging/v2/batch`：
  - UA：`claude-code/2.1.185`
  - beta：`oauth-2025-04-20`
  - `x-service-name=claude-code`
- 事件类型：
  - `ClaudeCodeInternalEvent`：462
  - `GrowthbookExperimentEvent`：5
- telemetry env 分布：
  - `version=2.1.185`
  - `version_base=2.1.185`
  - `build_time=2026-06-20T06:38:30Z`
  - `node_version=v24.3.0`
- `preNormalizedModel` 未出现有效值，`flags` 未出现有效值。

## Upgrade Impact

- 必须升级默认版本画像和账号迁移。
- 必须将 `2.1.185` 纳入 CCH 的 `2.1.172` / `2.1.173` 分支。
- 必须更新 GrowthBook UA 到 `Bun/1.4.0`。
- `cc_version` 算法不变。
- `MESSAGE_BETA_TOKENS` 主请求常量当前与 Opus 主请求一致；Haiku 辅助请求 beta 差异不进入本次默认主画像改造。
