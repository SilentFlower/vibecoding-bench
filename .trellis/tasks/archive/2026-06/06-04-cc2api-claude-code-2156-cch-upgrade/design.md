# cc2api Claude Code 2.1.156 兼容升级与 CCH 逆向设计

## Technical Design

### 输入资料

- 使用 `http_capture.jsonl` 做结构分析，但分析脚本默认只输出路径、headers key、字段名、计数、hash、CCH 短值，不打印 token、prompt、响应全文。
- 使用 `20260604-024430.flow` 作为必要时的 mitmproxy 原始复核材料。
- 使用 `/root/project/cc2api/src/service/rewriter.rs`、`telemetry.rs`、`gateway.rs`、`model/identity.rs`、`service/oauth.rs` 作为主要改造点。

### 版本指纹边界

`2.1.156` 兼容应集中为可配置版本 profile，避免再次把 `2.1.156` 散落到多个模块。profile 至少包含：

- `version`
- `version_base`
- `build_time`
- Claude Code UA：`claude-code/<version>`
- Claude CLI UA：`claude-cli/<version> (external, cli)`
- `X-Stainless-Package-Version`
- `X-Stainless-Runtime-Version`
- message beta token 集合
- endpoint header profile
- telemetry endpoint 版本
- CCH 策略

### Header Profile

2.1.156 不能只用一个全局 header 模板。抓包显示不同 endpoint 的 UA、beta 和附加字段不同，设计上应拆成 endpoint profile：

- `/v1/messages`：
  - `User-Agent=claude-cli/2.1.156 (external, cli)`
  - `anthropic-version=2023-06-01`
  - `anthropic-dangerous-direct-browser-access=true`
  - `x-app=cli`
  - `X-Stainless-Package-Version=0.94.0`
  - `X-Stainless-Runtime=node`
  - `X-Stainless-Runtime-Version=v24.3.0`
  - `X-Stainless-Lang=js`
  - `X-Stainless-OS`、`X-Stainless-Arch` 来自账号环境 profile
  - `X-Claude-Code-Session-Id` 与 `metadata.user_id.session_id` 对齐
  - `x-client-request-id` 每次请求生成
- `/api/event_logging/v2/batch`：
  - `User-Agent=claude-code/2.1.156`
  - `anthropic-beta=oauth-2025-04-20`
  - `x-service-name=claude-code`
- `/api/eval/{clientKey}`：
  - `anthropic-beta=oauth-2025-04-20`
  - 抓包中 UA 为 `Bun/1.3.14`，实现时需要决定是模拟 Bun UA 还是保守透传真实客户端 UA。
- `/v1/code/triggers`：
  - `anthropic-beta=ccr-triggers-2026-01-30`
  - `anthropic-client-platform=claude_code_cli`
  - `anthropic-version=2023-06-01`
  - `x-organization-uuid` 来自账号组织信息。
- `/v1/mcp_servers`：
  - `anthropic-beta=mcp-servers-2025-12-04`
  - `anthropic-version=2023-06-01`

cc2api 当前 API 模式固定 `X-Stainless-Package-Version=0.70.0`，需要升级到 2.1.156 抓包中的 `0.94.0`，否则即使 UA 版本正确，header 指纹仍会漂移。

### 遥测兼容

抓包显示 2.1.156 使用 `/api/event_logging/v2/batch`，请求体顶层仍是：

```json
{"events":[{"event_type":"ClaudeCodeInternalEvent","event_data":{}}]}
```

但事件数量和事件名远多于 cc2api 当前单一 `tengu_api_success`。设计上分两层：

- 拦截/改写层：真实客户端发来的 v2 batch 必须能识别并改写身份、env、process、auth、user_attributes。
- 代发层：自动遥测至少改为 v2 endpoint，并逐步用模板库生成更接近 2.1.156 的事件序列。

### 请求头和 body schema

`/v1/messages` 的 header profile 应覆盖抓包中的新版 beta token 和 Stainless 指纹。body 改写应避免删除真实客户端字段：

- `context_management.edits`
- `diagnostics.previous_message_id`
- `output_config.effort`
- `thinking.type`
- `tools` 中的新版工具名

API 注入模式可以先做到“不过度删除 + 必要字段补齐”，不强行完整模拟所有工具定义。

### CCH / cc_version 逆向

当前 cc2api 的两段算法需要分开判断：

- `cc_version` 后缀：2.1.156 binary 中仍是固定 salt `59cf53e54c78` + 首条用户消息字符串索引 `[4,7,20]` + version 后取 SHA256 前 3 位。cc2api 当前使用 UTF-8 字节位置，遇到中文/emoji 会错误；主会话还需要注意输入源是归一化前内部 transcript，不是最终 `/v1/messages` body。
- `cch`：当前按 body with `cch=00000` 计算 seeded xxhash64 低 20 bits；抓包中 16 条带 billing 的请求均不匹配。
- 规划期深入研究显示 2.1.156 native binary 仍包含旧 salt、`cch=00000` 和 billing 模板；`cc_version` 公式可定位，`cch` 替换点仍未定位。`xxHash64` 字符串目前更像 Bun/JavaScriptCore runtime 符号，不能直接证明应用层 CCH 使用旧 xxhash64 公式。

逆向路径：

1. 先建立离线 fixture：从抓包提取每条 `/v1/messages` 的安全摘要、billing 行、body hash、结构字段、第一用户消息 hash、system block hash。
2. 设计 controlled capture 矩阵：同 prompt 多次、不同 model、首轮/多轮、短 prompt/长 prompt。
3. 先修正 `cc_version` 的 JS 字符串索引语义，并把主会话/side query 输入源区分写入测试。
4. 验证旧 CCH 算法在原始 body、canonical JSON、不同字段删除版本、不同占位符替换时是否匹配；当前研究结果是这些常见候选全部 `0/16` 命中。
5. 如果仍不匹配，检查 npm 包安装产物中是否可定位 CCH 替换点，或用受控运行期 hook 捕获 SDK 发出前的 body。只做本地代码阅读和算法复现，不泄露凭证。
6. 产出版本化策略：
   - `2.1.81`：保留旧算法。
   - `2.1.156`：只有在算法复现后才开启 rewrite；否则对真实 Claude Code 客户端透传原始 billing 行，对 API 注入模式 strip 或标记 unsupported。

### Rollout / Rollback

- 先加测试和版本 profile，再替换默认 profile。
- 所有 2.1.156 行为应保留 feature flag 或 profile 回退能力。
- 如果 CCH 算法未解出，不发布伪造算法，只发布保守透传/strip 策略。
