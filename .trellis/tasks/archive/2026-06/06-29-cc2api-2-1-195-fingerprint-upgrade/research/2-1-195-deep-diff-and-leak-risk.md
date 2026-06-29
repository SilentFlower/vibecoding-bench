# Claude Code 2.1.195 深度差异与特征泄露风险

## 范围

- 证据来源：任务本地原始抓包 `evidence/run-23594999fa77/`。
- 对照来源：已归档的 2.1.173、2.1.185、2.1.187 脱敏研究记录，以及当前 `cc2api` 代码。
- 安全边界：本文只记录 endpoint、header 名和值、字段集合、计数、版本号、算法结论和风险判断；不记录 token、Cookie、Authorization、邮箱、账号 UUID、完整 prompt、完整响应正文或原始 flow。

## 结论摘要

2.1.195 相对 2.1.187 的确定变化很集中：

- Claude Code 版本：`2.1.187` -> `2.1.195`。
- build time：`2026-06-23T16:59:46Z` -> `2026-06-26T01:00:56Z`。
- Node / Stainless runtime：`v24.3.0` -> `v26.3.0`。
- allowed range 上限：`2.1.187` -> `2.1.195`。

2.1.195 没变的关键协议面：

- `X-Stainless-Package-Version=0.94.0`。
- `/v1/messages` 主请求 beta 顺序与 2.1.187 的 Opus `[1m]` 样本一致。
- Haiku 探测 / 标题请求 beta 与 2.1.187 一致。
- `cc_version` 后缀算法不变。
- CCH seed 与 `2.1.172+` top-level 规范化规则不变。
- telemetry shape 仍是 `ClaudeCode2185`。
- GrowthBook UA 仍是 `Bun/1.4.0`。
- MCP capability、MCP protocol、code triggers beta、event logging path 未发现变化。

## 与之前版本的差异矩阵

| 项 | 2.1.173 | 2.1.185 | 2.1.187 | 2.1.195 |
|---|---|---|---|---|
| CLI UA | `claude-cli/2.1.173 (external, cli)` | `claude-cli/2.1.185 (external, cli)` | `claude-cli/2.1.187 (external, cli)` | `claude-cli/2.1.195 (external, cli)` |
| Code UA | `claude-code/2.1.173` | `claude-code/2.1.185` | `claude-code/2.1.187` | `claude-code/2.1.195` |
| build_time | `2026-06-11T01:23:13Z` | `2026-06-20T06:38:30Z` | `2026-06-23T16:59:46Z` | `2026-06-26T01:00:56Z` |
| runtime | `v24.3.0` | `v24.3.0` | `v24.3.0` | `v26.3.0` |
| Stainless package | `0.94.0` | `0.94.0` | `0.94.0` | `0.94.0` |
| GrowthBook UA | `Bun/1.3.14` | `Bun/1.4.0` | `Bun/1.4.0` | `Bun/1.4.0` |
| telemetry shape | `ClaudeCode2173` | `ClaudeCode2185` | `ClaudeCode2185` | `ClaudeCode2185` |
| CCH profile | `2.1.172+` | `2.1.172+` | `2.1.172+` | `2.1.172+` |
| cc_version | 同公式 | 同公式 | 同公式 | 同公式 |

判断：2.1.195 不是一次大协议换代，最容易暴露的是“只升级 UA 但 runtime/env 仍停在 v24.3.0”这种组合特征。

## 2.1.195 抓包事实

流量概览：

- 总 flow：86。
- `/v1/messages`：31 条。
- `/api/event_logging/v2/batch`：43 批，829 个事件。
- `/mcp-registry/v0/servers`：4 条。
- bootstrap / GrowthBook / OAuth settings / grove / penguin / MCP servers / code triggers 各 1 条。

`/v1/messages`：

- 31 条全部为 `?beta=true`。
- 29 条 Opus 主请求：`model=claude-opus-4-8`、`max_tokens=64000`、`stream=true`、`thinking={"type":"adaptive"}`、10 个工具。
- 1 条 Haiku 非流探测：`max_tokens=1`，无 system，无 billing。
- 1 条 Haiku 流式标题：`max_tokens=32000`、`stream=true`、`thinking={"type":"disabled"}`、无工具、带 billing。
- 30 条带 billing，`cc_version` 分布为 `2.1.195.aff` 29 条、`2.1.195.113` 1 条。
- 30 条 billing 都带 5 位十六进制 CCH。

`/v1/messages` body 顶层 key 顺序：

- Haiku 非流探测：`model,max_tokens,messages,metadata`。
- Haiku 流式标题：`model,messages,system,tools,metadata,max_tokens,thinking,temperature,output_config,stream`。
- Opus 主请求：`model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,diagnostics,stream`。

header 画像：

- `/v1/messages`：`User-Agent=claude-cli/2.1.195 (external, cli)`，`X-Stainless-Runtime-Version=v26.3.0`。
- `/api/event_logging/v2/batch`：`User-Agent=claude-code/2.1.195`，`x-service-name=claude-code`。
- `/api/eval/*` 和 `HEAD /`：`User-Agent=Bun/1.4.0`。
- `/api/claude_code_penguin_mode` 和 `/v1/mcp_servers`：`User-Agent=axios/1.15.2`。
- `/api/oauth/account/settings`、`/api/claude_code_grove`、`/mcp-registry/*`：`User-Agent=claude-cli/2.1.195 (external, cli)`。

telemetry：

- `env.version=2.1.195`。
- `env.version_base=2.1.195`。
- `env.build_time=2026-06-26T01:00:56Z`。
- `env.node_version=v26.3.0`。
- 本样本环境组合为 `linux/x64/tmux/bash/docker/debian/12`。
- `event_data.email` 未出现，符合 `ClaudeCode2185` shape。
- `additional_metadata` 里出现大量字段，常见包括 `subscription_type`、`renderer_mode`、`queryChainId`、`requestId`、`messageID`、`toolName`、`durationMs`、`preNormalizedModel`、token/cost/cache 统计等。

## 当前实现已覆盖的关键点

- 默认 profile、默认版本、build time、allowed range 已指向 `2.1.195`。
- `STAINLESS_RUNTIME_VERSION` 已是 `v26.3.0`。
- `PROFILE_2_1_195` 已加入 registry，并保留 `2.1.187` / `2.1.185` / `2.1.173` 回滚。
- header 改写会按账号 `canonical_env.version` 查 profile，因此回滚 profile 可继续使用对应旧 runtime。
- CCH 白名单已加入 `2.1.195`，仍使用 `2.1.172+` top-level 规范化。
- `cc_version` 测试已覆盖 `2.1.195.113` 和 `2.1.195.aff` 的脱敏样本。
- settings/DB 迁移已覆盖旧默认 profile + 旧默认 allowed range 成对升级，并更新账号 `canonical_env.version/version_base/build_time/node_version`。

## 仍可能泄露的特征面

### 1. 辅助 endpoint header 顺序

`/v1/messages` 的 header 顺序与抓包一致，是主风险面里最关键的一项。

但 2.1.195 抓包中若干辅助 endpoint 的 header 顺序与当前 `wire_header_order` 声明不完全一致：

- event logging 抓包顺序：`Accept, Content-Type, User-Agent, x-service-name, Authorization, anthropic-beta, Content-Length, Accept-Encoding, Host, Connection`。
- 当前代码顺序：`Accept, Accept-Encoding, Authorization, Content-Type, User-Agent, anthropic-beta, x-service-name, Connection, Host`。
- bootstrap 抓包顺序：`Accept, Content-Type, User-Agent, Authorization, anthropic-beta, Accept-Encoding, Host, Connection`。
- 当前代码顺序：`Accept, Accept-Encoding, Authorization, Content-Type, User-Agent, anthropic-beta, Connection, Host`。
- `/v1/mcp_servers` 抓包顺序里 `MCP-Protocol-Version` 大小写是首字母大写形式，当前 casing map 倾向 `mcp-protocol-version` 小写。

风险判断：中高。header 值和集合比顺序更重要，但辅助端点会稳定重复，顺序如果被上游或风控侧纳入特征，可能暴露 reqwest/gateway 生成痕迹。需要用线上网关实际出站抓包验证，而不是只看 `HashMap` 或单测。

### 2. OAuth `TokenTester` 的 Haiku 探测 beta 过宽

真实 2.1.195 Haiku `max_tokens=1` 探测 beta 是窄集合：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05
```

`TokenTester` 发送同类 `claude-haiku-4-5-20251001` / `max_tokens=1` 请求时仍使用通用 `MESSAGE_BETA_TOKENS`。这不是普通 `/v1/messages` 热路径，但它是真实上游调用，可能在新增账号或测试 token 时留下非真实组合。

风险判断：中。建议后续把 token test 改为复用 `HAIKU_PROBE_BETA_TOKENS`，并按真实 header 顺序发送。

### 3. telemetry additional_metadata 覆盖不足

当前自动 telemetry 的 env 主字段已对齐 2.1.195，但抓包中 `additional_metadata` 的字段远多于当前构造逻辑：

- 抓包常见字段包括 `queryChainId`、`requestId`、`messageID`、`toolName`、`durationMs`、`preNormalizedModel`、cache/token/cost 统计、tool use 统计等。
- 当前实现主要构造 `renderer_mode`、`entrypoint`、`provider`、`model`、`subscription_type`、`attempt` 等基础字段。

风险判断：中。telemetry 不是 `/v1/messages` 鉴权必需路径，但如果开启 auto telemetry，结构稀疏和字段组合可能暴露“模拟遥测”。短期建议远程灰度时观察 auto telemetry 是否必须开启；中期按事件名逐步补齐 `additional_metadata` 的非敏字段。

### 4. 账号 canonical env 的跨通道一致性

2.1.195 后 `env.node_version`、`X-Stainless-Runtime-Version`、telemetry env 必须同时是 `v26.3.0`。任何旧账号残留 `v24.3.0` 都会形成高置信异常组合：

- UA：`2.1.195`
- billing：`cc_version=2.1.195.*`
- telemetry/build_time：`2.1.195`
- 但 node/runtime：`v24.3.0`

风险判断：高。代码已做迁移，但远程部署后必须查 DB 分布，不能只看新镜像日志。

### 5. 请求体字段顺序与 serde_json 重序列化

真实抓包中的 `/v1/messages` 顶层字段顺序稳定。当前 rewriter 会把 body 反序列化为 `serde_json::Value` 后再序列化，`cc2api` 当前未启用 `serde_json/preserve_order`。

风险判断：中。CCH 已按改写后的最终 body 计算，所以不会因为自身重序列化造成 CCH 错；但“字段顺序不像真实 Claude Code”仍可能作为独立 wire 特征。主请求顶层 key 集合对齐，顺序需要靠实际出站抓包验证。

### 6. TLS / ALPN 仍是单独的传输层指纹面

当前 TLS 层用自定义 Node.js 指纹，ALPN 只声明 `http/1.1`。2.1.195 这次抓包摘要主要覆盖 HTTP 层，没有证明当前 TLS/JA3/ALPN 与真实 Claude Code 2.1.195 完全一致。

风险判断：中高。近期封号严重时，TLS/连接复用/代理出口 ASN 与 HTTP 指纹一样重要。本任务没有逆向 TLS，只能说明 HTTP 层已明显收敛。

### 7. `working_dir` 默认真值透传

settings 默认 `passthrough_working_dir=true`，这会把真实工作目录放入 system prompt 的环境块。它不是版本画像字段，但可能泄露容器路径、项目名或自动化环境。

风险判断：中。这个默认是为了不误导模型 cwd，但对“账号养号/反检测”场景不一定最优。若目标是尽量少暴露宿主特征，可以考虑对生产账号关闭工作目录透传，或把路径规范化到账号预设。

### 8. 代理连接池和跨账号连接复用

当前同一 `proxy_url` 会复用同一个 reqwest client。不同账号如果配置相同代理，会共享底层连接池行为。

风险判断：中。真实 Claude Code 是单账号本地进程视角；多账号共享同一代理连接池可能让连接复用、TCP keepalive、请求时序看起来不像独立用户。高风险账号建议按账号隔离代理，必要时关闭代理 client pool 做对照。

## 建议的下一步验证

1. 部署后从远程网关重新抓一轮出站包，和 `23594999fa77` 对比，而不是只看代码常量。
2. 查远程 DB：
   - `settings.claude_code_version_profile=2.1.195`
   - `settings.allowed_claude_code_versions=2.1.89-2.1.195`
   - 所有账号 `canonical_env.version/version_base/build_time/node_version` 为 `2.1.195 / 2.1.195 / 2026-06-26T01:00:56Z / v26.3.0`
3. 定向抓 token test 请求，确认是否仍使用通用 beta；若会频繁触发，优先修成 Haiku probe 窄 beta。
4. 抓 auto telemetry 请求，检查 event logging / bootstrap / MCP servers 的真实出站 header 顺序和大小写。
5. 用 TLS 指纹观测服务对远程出口做一次 Node 26 对齐验证，至少记录 ALPN、cipher、extension、supported groups 是否符合目标。
6. 针对高风险账号做 A/B：关闭 auto telemetry、关闭工作目录透传、隔离代理连接池，观察 429/封号/风控提示差异。

## 优先级判断

短期必须验收：

- 远程 DB 中账号 env 是否全部迁到 2.1.195 / v26.3.0。
- 真实出站 `/v1/messages` 是否仍是 2.1.195 + v26.3.0 + 正确 beta + 正确 CCH。
- `TokenTester` 是否在生产新增账号流程中频繁触发。

中期建议修复：

- 对齐辅助 endpoint 的 header 顺序和 `MCP-Protocol-Version` casing。
- `TokenTester` 使用 Haiku probe 窄 beta。
- 补齐 telemetry `additional_metadata` 的安全字段，或明确默认关闭 auto telemetry。

长期风险：

- TLS/ALPN、连接复用、代理出口、系统 prompt 环境路径等不属于版本 profile，但可能是封号更主要的特征来源。
