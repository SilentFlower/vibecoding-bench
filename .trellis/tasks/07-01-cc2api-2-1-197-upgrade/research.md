# 脱敏抓包研究记录

## 数据来源

- 远程环境：`.deploy/vibecoding-bench.env` 指向的主机。
- 抓包 run：`d72b00a1257b`。
- 远程目录：`data/flows/6-29/4876/d72b00a1257b`。
- 文件规模：`capture_index.json` 约 229 KB，`http_capture.jsonl` 约 28.5 MB，`stats.jsonl` 约 97 KB。
- 安全边界：只提取协议字段摘要，不记录 Authorization、Cookie、账号邮箱、prompt、响应正文。

## 2.1.197 发布事实

- npm package：`@anthropic-ai/claude-code@2.1.197`。
- dist-tag：`latest=2.1.197`，`next=2.1.197`，`stable=2.1.185`。
- 发布时间：2026-06-30 13:31:18 UTC。

## 端点摘要

| 数量 | 方法 | Host | Path | 状态 |
|---:|---|---|---|---|
| 71 | POST | api.anthropic.com | `/api/event_logging/v2/batch` | 200 |
| 68 | POST | api.anthropic.com | `/v1/messages` | 200 |
| 4 | GET | api.anthropic.com | `/mcp-registry/v0/servers` | 200 |
| 1 | GET | api.anthropic.com | `/api/claude_cli/bootstrap` | 200 |
| 1 | GET | api.anthropic.com | `/v1/mcp_servers` | 200 |
| 1 | GET | api.anthropic.com | `/v1/code/triggers` | 200 |

## Bootstrap 摘要

- 请求：`GET /api/claude_cli/bootstrap?entrypoint=cli&model=claude-sonnet-5`。
- UA：`claude-code/2.1.197`。
- beta：`oauth-2025-04-20`。
- 响应模型选项摘要：包含 `claude-fable-5[1m]`。

## Telemetry 摘要

event logging env 中出现的版本画像：

```text
version=2.1.197
version_base=2.1.197
build_time=2026-06-29T19:08:42Z
node_version=v26.3.0
```

## `/v1/messages` 摘要

| 模型 | 数量 | `context-1m` beta | body 提及 `[1m]` | body 提及 sonnet |
|---|---:|---:|---:|---:|
| `claude-haiku-4-5-20251001` | 2 | 0 | 0 | 0 |
| `claude-sonnet-5` | 66 | 66 | 66 | 66 |

用户补充约束：`claude-sonnet-4-6` 不带 `context-1m-2025-08-07`。因此抓包结论只能支持精确放行 `claude-sonnet-5`，不能推导成宽泛放行所有 Sonnet。

Sonnet 5 主请求 beta：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Sonnet 5 主请求 body 顶层字段顺序：

```text
model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,diagnostics,stream
```

其中 65 条包含 `diagnostics`，1 条为：

```text
model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,stream
```

Sonnet 5 主请求 billing 形态：

```text
cc_version=2.1.197.<suffix>; cc_entrypoint=cli; cch=<5hex>;
```

Sonnet 5 主请求首条 user message 形态：

```text
text_blocks=2 lens=[371, 108]
```

当前日期上下文摘要：

```text
Today's date is 2026-06-30.
```

其中撇号为 ASCII `U+0027`，日期分隔符为 `-`。

## `cc_version` 后缀复算

已在远程侧用抓包正文复算，只回传脱敏统计：

- Haiku 带 billing header 的样本：`cc_version=2.1.197.197`，用首条 user text block 复算后缀命中 `197`。
- Sonnet 5 主请求样本：实际后缀均为 `439`；首条 user message 有两个 text block，按第一个 text block 复算得到 `72f`，按最后一个 text block 复算得到 `439`。
- 结论：`2.1.197` 的 `cc_version` 后缀仍沿用现有算法，即 `sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]`，且多 text block 时必须取最后一个 user text block。

## CCH 复算

已用仓库已知 `2.1.169` 样本校准远程纯 Python `xxhash64` 实现，能得到仓库测试期望 `cch=27300`；同时用本机 `@anthropic-ai/claude-code@2.1.197` first-party localhost 假上游样本校准，命中本地生成的 `cch=<5hex>`。本机动态验证期间临时将 `api.anthropic.com` 指向 `127.0.0.1`，使用自签本地证书和 dummy OAuth token，未向真实 Anthropic 发请求。

静态逆向确认：

```text
tTn(e,t) 生成 x-anthropic-billing-header，其中 firstParty && Eu() 或 vertex 时放入 cch=00000
cc_version 后缀函数仍为 sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).slice(0,3)
```

本机 first-party 动态样本命中规则：

```text
xxhash64(input, 0x4D659218E32A3268) & 0xFFFFF
input = 最终 body 字节，将 cch=<5hex> 还原为 cch=00000 后：
  - top-level model 字符串值置为 ""
  - 删除 top-level max_tokens
  - 保留 top-level diagnostics
```

对远程 `2.1.197` 抓包样本复算结果：

| 模型 | 样本数 | 完整 body + 旧 seed | model 置空 + 旧 seed | model 置空 + 删除 max_tokens + 旧 seed | model 置空 + 删除 max_tokens + 删除 diagnostics + 旧 seed |
|---|---:|---:|---:|---:|---:|
| `claude-haiku-4-5-20251001` | 1 | 0 | 0 | 1 | 1 |
| `claude-sonnet-5` | 66 | 0 | 0 | 66 | 1 |

结论：`2.1.197` 继续使用 seed `0x4D659218E32A3268`，CCH 输入规则与 `2.1.172` / `2.1.195` 的 2172+ profile 一致：最终 body 字节中将 `cch` 还原为占位符后，top-level `model` 置空、删除 top-level `max_tokens`、删除 top-level `fallbacks`。`diagnostics` 必须保留；删除 `diagnostics` 会导致 Sonnet 5 65/66 条不命中。当前远程样本没有 top-level `fallbacks`，但二进制字符串与既有 2172+ 规则均支持继续删除 top-level `fallbacks`。

## Telemetry 结构核对

抓包中的 `/api/event_logging/v2/batch`：

- 请求 UA：`claude-code/2.1.197`。
- 请求 header beta：`oauth-2025-04-20`。
- event env 固定包含 `version=2.1.197`、`version_base=2.1.197`、`build_time=2026-06-29T19:08:42Z`、`node_version=v26.3.0`、`shell=bash`、`is_running_with_bun=true`。
- event_data 字段包含 `event_name`、`client_timestamp`、`model`、`user_type`、`betas`、`env`、`entrypoint`、`is_interactive`、`client_type`、`process`、`additional_metadata`、`auth`、`event_id`、`device_id`、`session_id`。
- `additional_metadata` 非空，结构看起来仍符合现有 `TelemetryShape::ClaudeCode2185`，未从该抓包看到新的 telemetry shape。
- event `model` 和 `betas` 会反映 Sonnet 5 1M：大量事件 model 为 `claude-sonnet-5[1m]`，betas 包含 `context-1m-2025-08-07`。

## Opus 抓包 `38335b80e9ef` 复核

### 数据来源

- 远程环境：`.deploy/vibecoding-bench.env` 指向的主机。
- 抓包 run：`38335b80e9ef`。
- 远程目录：`data/flows/6-29/4879/38335b80e9ef`。
- 文件规模：`capture_index.json` 约 40 KB，`http_capture.jsonl` 约 2.1 MB，`stats.jsonl` 约 18 KB，`.flow` 约 79 MB。
- 安全边界：完整抓包只临时拉到 `/tmp` 分析；本记录只保留 endpoint、header 安全枚举、body 顶层字段、模型名和 hash 命中统计。

### 端点摘要

| 数量 | 方法 | Host | Path |
|---:|---|---|---|
| 13 | POST | api.anthropic.com | `/api/event_logging/v2/batch` |
| 6 | POST | api.anthropic.com | `/v1/messages?beta=true` |
| 3 | POST | mcp-proxy.anthropic.com | `/v1/mcp/...` |
| 1 | GET | api.anthropic.com | `/api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8` |
| 1 | POST | api.anthropic.com | `/api/eval/sdk-zAZezfDKGoZuXXKe` |

### `/v1/messages` 摘要

| 模型 | 数量 | billing 样本 | `context-1m` beta | `max_tokens` | `diagnostics` |
|---|---:|---:|---:|---:|---:|
| `claude-haiku-4-5-20251001` | 2 | 1 | 0 | 1 / 32000 | 0 |
| `claude-opus-4-8` | 4 | 4 | 4 | 4 / 64000 | 4 |

6 条 `/v1/messages` 的请求头摘要：

```text
User-Agent=claude-cli/2.1.197 (external, cli)
X-Stainless-Package-Version=0.94.0
X-Stainless-Runtime=node
X-Stainless-Runtime-Version=v26.3.0
X-Stainless-Timeout=600
anthropic-version=2023-06-01
x-app=cli
```

4 条 Opus 主请求的 beta 顺序与 Sonnet 5 主请求一致，且 `context-1m-2025-08-07` 位于 `oauth-2025-04-20` 后、`interleaved-thinking-2025-05-14` 前：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

4 条 Opus 主请求 body 顶层字段顺序：

```text
model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,diagnostics,stream
```

### `cc_version` 与 CCH 复算

复算只输出命中统计，不记录首条 user text、prompt 或响应正文。

| 范围 | 样本数 | `cc_version` 后缀命中 | CCH 命中 |
|---|---:|---:|---:|
| Opus 主请求 | 4 | 4 | 4 |
| Haiku 带 billing 辅助请求 | 1 | 1 | 1 |

Opus 样本的 billing 形态：

```text
cc_version=2.1.197.439; cc_entrypoint=cli; cch=<5hex>;
```

Haiku 辅助样本的 billing 形态：

```text
cc_version=2.1.197.197; cc_entrypoint=cli; cch=<5hex>;
```

结论：Opus 抓包继续命中当前 `2.1.197` 规则：

- `cc_version` 后缀沿用现有 SHA256 文本索引算法。
- CCH seed 仍是 `0x4D659218E32A3268`。
- CCH 输入仍是最终 body 字节，将 `cch=<5hex>` 还原为 `cch=00000` 后，top-level `model` 置空，删除 top-level `max_tokens` 和 `fallbacks`，保留 `diagnostics`。

### Bootstrap 与 Telemetry

Bootstrap：

```text
GET /api/claude_cli/bootstrap?entrypoint=cli&model=claude-opus-4-8
User-Agent=claude-code/2.1.197
anthropic-beta=oauth-2025-04-20
```

响应模型选项摘要中仍可见 `claude-fable-5[1m]`。

Telemetry env 摘要：

```text
version=2.1.197
version_base=2.1.197
build_time=2026-06-29T19:08:42Z
node_version=v26.3.0
```

Telemetry 事件中的模型摘要：

| 模型标记 | 事件计数 |
|---|---:|
| `claude-opus-4-8[1m]` | 208 |
| `claude-opus-4-8` | 3 |
| `claude-haiku-4-5-20251001` | 2 |

结论：`38335b80e9ef` 的 Opus 抓包符合本次升级后的 `2.1.197` 特征；没有发现需要在当前实现中追加修正的 Opus 差异。
