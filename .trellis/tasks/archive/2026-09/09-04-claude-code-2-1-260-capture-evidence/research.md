# Claude Code 2.1.260 脱敏抓包结论

## 数据来源与安全边界

- 2.1.260 生产抓包：`12a15859fced`、`1349e36bdf19`、`8b6129adc9fa`、
  `aed307de9913`、`2c2117af211c`。
- 2.1.257 基线：`0c3beffc2f35`、`2b9aeab66d11`、`9333aa5d1fe3`、
  `ea6d8e9bb665`，并复用上一轮 Fable 5.1 多轮结论。
- 原始文件只保存在根目录已忽略的 `data/evidence/` 和既有 `data/flows/`；没有把
  Authorization、Cookie、Token、账号、邮箱、prompt、响应正文或 `.flow` 提交到 Git。
- 脱敏分析脚本为 `research/analyze_capture.py`，生成的完整聚合 JSON 也位于忽略目录。
- `fixtures/claude-code-2.1.260-profile.json` 只含人工构造文本和可公开协议常量。

## 样本完整性

所有 2.1.260 run 的数据库版本快照均为 `2.1.260`。这些抓包创建在独立 effort
快照字段上线之前，因此数据库中的 `claude_effort_level` 为 `NULL`；这不影响请求正文
证据，Opus、Sonnet 和 Fable 5.1 主请求的 `output_config.effort` 均为 `max`，Haiku
主请求通过 `thinking.budget_tokens=31999` 表达预算。

| run | 页面选择 | 实际主模型 | 终态 | JSONL / index | raw / JSONL 全量 | flow / JSONL messages | 完成主请求 | raw-only message | 最大 messages |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `12a15859fced` | `opus[1m]` | `claude-opus-5` | success | 419 / 419 | 429 / 419 | 56 / 54 | 45 | 2 | 133 |
| `1349e36bdf19` | `sonnet` | `claude-sonnet-5` | stopped | 69 / 69 | 71 / 69 | 5 / 5 | 2 | 0 | 5 |
| `8b6129adc9fa` | `claude-fable-5-1` | `claude-fable-5-1` | success | 115 / 115 | 122 / 115 | 12 / 10 | 6 | 2 | 20 |
| `aed307de9913` | `claude-fable-5-1` | `claude-fable-5-1` | success | 224 / 224 | 232 / 224 | 24 / 22 | 15 | 2 | 47 |
| `2c2117af211c` | `haiku` | `claude-haiku-4-5-20251001` | success | 172 / 172 | 176 / 172 | 25 / 25 | 19 | 0 | 37 |

`capture_index.total_flows`、index entries 数和 JSONL 行数逐 run 完全一致，说明结构化
索引自身没有截断。五份 raw `.flow` 合计 1030 条 Anthropic 流量，JSONL/index 合计
999 条；逐请求对账后 structured-only 为 0，raw-only 为 31：

- 6 条 `/v1/messages` 收到 200 headers，但 SSE 正文为 0 字节。
- 16 条 worker event stream 收到 200 headers，但长连接正文为 0 字节。
- 9 条后台请求没有 response：3 条 client presence、4 条 session archive、1 条 worker
  events、1 条 worker heartbeat。

31 条 raw-only flow 均带 flow error，recorder 没有把这些未完成响应写入 JSONL/index。
因此“index 完整”只能解释为完成型结构化记录一致，不能解释为 raw flow 中没有其他尝试；
其中只有 6 条 message 请求参与下文的 `cc_version`、CCH 和首字节超时分析，其余 25 条
只用于说明抓包关闭或长连接中断时的后台流量边界，不并入模型协议画像。

样本覆盖 Opus、Sonnet、Fable 5.1 和 Haiku。Opus、两份 Fable 5.1 与 Haiku 都覆盖
多轮；Opus 最长完成请求有 133 条 messages，已满足复杂多轮要求。

## 身份与传输画像

2.1.260 已确认身份：

| 字段 | 2.1.257 | 2.1.260 | 结论 |
| --- | --- | --- | --- |
| version / version_base | `2.1.257` | `2.1.260` | 变化 |
| build time | `2026-09-01T05:28:54Z` | `2026-09-03T19:41:35Z` | 变化 |
| CLI UA | `claude-cli/2.1.257 (external, cli)` | `claude-cli/2.1.260 (external, cli)` | 仅版本变化 |
| Claude Code UA | `claude-code/2.1.257` | `claude-code/2.1.260` | 仅版本变化 |
| Stainless package | `0.112.1` | `0.112.1` | 不变 |
| Stainless runtime | `node` / `v26.3.0` | `node` / `v26.3.0` | 不变 |
| hello / eval UA | `Bun/1.4.1` | `Bun/1.4.1` | 不变 |
| messages timeout | `600` | `600` | 不变 |
| messages encoding | `gzip, deflate, br, zstd` | 同左 | 不变 |

2.1.260 的 `/v1/messages` header 顺序在五份 raw flow 中一致：

```text
Accept, Authorization, Content-Type, User-Agent,
X-Claude-Code-Session-Id, X-Stainless-Arch, X-Stainless-Lang, X-Stainless-OS,
X-Stainless-Package-Version, X-Stainless-Retry-Count, X-Stainless-Runtime,
X-Stainless-Runtime-Version, X-Stainless-Timeout,
anthropic-beta, anthropic-dangerous-direct-browser-access, anthropic-version,
x-app, x-client-request-id, Connection, Host, Accept-Encoding, Content-Length
```

telemetry、bootstrap、eval、hello、triggers 和 MCP 的 header 顺序也与 2.1.257
基线一致。旧 Opus 样本 43/44 条 messages 额外带 `x-cc-atis`，但另外三份 2.1.257
基线和全部 2.1.260 样本均没有该 header；这更像账号/实验条件，而不是足以确认的版本
删除项，当前不能据此新增或硬删除协议字段。

## Endpoint 结论

按动态 session/eval ID 归一化后，Opus、Fable 5.1 和 Haiku 的 2.1.257/2.1.260
endpoint 集合完全相同，没有发现 2.1.260 新 endpoint。主要请求族仍包括：

- `HEAD /api/hello`
- `POST /api/eval/{id}`
- `GET /api/claude_cli/bootstrap`
- `POST /api/event_logging/v2/batch`
- `POST /v1/messages`
- `/v1/code/sessions/{id}/...` 与 `/v1/sessions/{id}`
- `/v1/code/triggers`、`/v1/mcp_servers`、`/mcp-registry/v0/servers`
- `/api/oauth/account/settings`、grove、penguin mode、notification preferences、
  ultrareview quota

五份 2.1.260 JSONL 中所有已落盘响应状态均为 200。Sonnet run 虽然终态是 stopped，
但两条 Sonnet 主请求都收到完整 SSE `message_stop`，不能把 run 终态解释成协议失败。

## `/v1/messages` 差异

### 主模型矩阵

| 模型 | 2.1.260 样本 | max_tokens | thinking | fallback | 相对 2.1.257 |
| --- | ---: | ---: | --- | --- | --- |
| Opus 5 | 45 完成 + 2 零正文 | 64000 | `type=adaptive, display=updates` | 无 | 去 redact beta，新增 display beta/字段 |
| Sonnet 5 | 2 完成 | 64000 | `type=adaptive, display=updates` | 无 | 无精确 2.1.257 Sonnet 基线 |
| Fable 5.1 | 21 完成 + 4 零正文 | 64000 | `type=adaptive, display=updates` | 字符串 `default` | 新增 per-turn beta |
| Haiku | 19 完成 | 32000 | `budget_tokens=31999, type=enabled, display=updates` | 无 | 去 redact beta，新增 display beta/字段 |

Opus、Sonnet、Fable 5.1 的 `output_config.effort=max`。Haiku 主请求没有
`output_config`。`thinking` 内部字段顺序也稳定：Opus/Sonnet/Fable 5.1 为
`type,display`，Haiku 为 `budget_tokens,type,display`。

Opus `[1m]` 主请求保留 `context-1m-2025-08-07`，位置仍在 `oauth` 后、
`interleaved-thinking` 前。Sonnet、Fable 5.1 和 Haiku 主请求不带 1M beta。
本轮没有 2.1.260 Fable 5.1 `[1m]` 入口样本，因此不能从无后缀 Fable 样本外推
`[1m]` 解析行为。

### 2.1.260 精确 beta

Opus 5 `[1m]`：

```text
claude-code-20250219,oauth-2025-04-20,context-1m-2025-08-07,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,fallback-credit-2026-06-01,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Sonnet 5：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Fable 5.1：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,per-turn-control-2026-07-01,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-07-01,fallback-credit-2026-06-01,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Haiku main（有 diagnostics）：

```text
oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,claude-code-20250219,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Haiku main（无 diagnostics）只在上面基础上移除 `claude-code-20250219`。Haiku
probe、结构化 title 和 1024 非流式辅助请求的精确 beta、max_tokens、thinking 和
字段顺序与 2.1.257 基线一致；不同父模型会让两条 title 中的一条带对应 fallback
token，这个变体在 2.1.257 已经存在，不是 2.1.260 新变化。

### 顶层字段顺序

Opus/Sonnet 主请求：

```text
model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,diagnostics,stream
```

Fable 5.1 主请求：

```text
model,messages,system,tools,metadata,max_tokens,thinking,context_management,fallbacks,output_config,diagnostics,stream
```

Haiku 主请求：

```text
model,messages,system,tools,metadata,max_tokens,thinking,context_management,diagnostics,stream
```

每类都有一条无 diagnostics 变体时，只移除 `diagnostics`，其余相对顺序不变。
Fable 5.1 每条主请求有 5 个 system block，其他主模型为 4 个；该差异在 2.1.257
Fable 5.1 已存在。精确 Claude Code 身份块仍是
`You are Claude Code, Anthropic's official CLI for Claude.`。

大型客户端 system 指令块的脱敏 hash 在 Opus/Fable 跨版本比较中有变化，而身份块、
billing 块和若干固定能力块不变。这些正文由原生客户端发送，当前任务既不提交也不反推
其内容；不能仅凭长度/hash 去改 cc2api 的公开身份块或合成扩展正文。

## `cc_version` 与 CCH

### `cc_version`

2.1.260 的 117 条带 billing 请求全部命中既有算法：

```text
sha256("59cf53e54c78" + text[4] + text[7] + text[20] + version).hex()[0:3]
```

- JavaScript UTF-16 code unit 索引语义不变。
- 首条 user message 有多个 text block 时仍取最后一个 text block。
- 最后 text block：117/117 命中；错误取第一个 text block：24/117 命中，命中的主要是
  本来就只有一个文本块的辅助请求，不能据此使用第一个 block。

### CCH

- seed 继续是 `0x4D659218E32A3268`。
- legacy seed `0x6E52736AC806831E`：0/117 命中。
- 2156 seed + 完整 body：0/117 命中。
- 公共归一化仍是：真实 CCH 还原为 `00000`，清空 top-level `model` 值，删除
  top-level `max_tokens`，保留其余字节序列和字段顺序。
- Fable 5.1 的 top-level `fallbacks="default"` 必须保留并参与 hash。
- 非 Fable 样本本身没有 top-level `fallbacks`，所以这些样本无法区分“删除”和
  “保留一个不存在的字段”；不能从它们外推未观察到的 fallback 行为。

| 请求族 | 样本 | `cc_version` | CCH 2156 + model/max | 再删除 fallbacks |
| --- | ---: | ---: | ---: | ---: |
| Opus main | 47 | 47 | 47 | 47 |
| Sonnet main | 2 | 2 | 2 | 2 |
| Fable 5.1 main | 25 | 25 | 25 | 0 |
| Haiku main | 19 | 19 | 19 | 19 |
| Haiku non-stream aux | 14 | 14 | 14 | 14 |
| Haiku title | 10 | 10 | 10 | 10 |
| 合计 | 117 | 117 | 117 | 92 |

5 条 `max_tokens=1` Haiku probe 没有 billing header，不进入上述分母。

## 2.1.257 Fable 5 基线修正

本轮回查 `2b9aeab66d11` 的 31 条真实 `claude-fable-5` 主请求，发现现有 cc2api
画像和旧任务结论存在历史漂移：

| 字段 | 真实 2.1.257 Fable 5 | cc2api 当前画像 |
| --- | --- | --- |
| fallbacks | 字符串 `"default"`，31/31 | `[{'model':'claude-opus-5'}]` |
| fallback beta | `server-side-fallback-2026-07-01` | `server-side-fallback-2026-06-01` |
| CCH | 保留 `fallbacks` 后 31/31 | 仅 Fable 5.1 保留 |
| thinking | `type=adaptive`，无 display | 相同 |
| bootstrap cwk | `marigold` | 2.1.257 统一 Fable key 为 `sorrel` |

这不是 2.1.260 新变化，但协议子任务必须一起修复，否则新增 2.1.260 profile 仍会继承
错误的 2.1.257 回滚行为。Fable 5 与 Fable 5.1 仍需按精确模型分别建模：两者在
2.1.257 都使用 `fallbacks="default"`，但 beta、thinking display、system block 和
bootstrap cwk 不完全相同。

本轮没有 2.1.260 Fable 5 样本。对 2.1.260 Fable 5 只能明确标记“证据不足”，不能
把 Fable 5.1 的 per-turn/display 画像无条件套给 Fable 5。

## Bootstrap

五份 2.1.260 bootstrap 都是 200 + Brotli，response 顶层字段顺序和 2.1.257
一致，`additional_model_options` 继续包含 `claude-fable-5-1[1m]`，
`client_data.cedar_basin` 继续为 `2027-08-31`。

| 实际查询模型 | cwk_cfg_key |
| --- | --- |
| `claude-opus-5` | `belladonna` |
| `claude-sonnet-5` | `pewter` |
| `claude-fable-5-1` | `sorrel` |
| `claude-haiku-4-5-20251001` | `null` |

现有 `EndpointProfile` 只有一个 Fable key 和一个 Opus key，无法同时表达 2.1.257
Fable 5=`marigold`、Fable 5.1=`sorrel`，也没有 Sonnet 5=`pewter`。协议实现应改为
按精确模型选择 bootstrap key，而不是继续扩充 family 级特例。

## Telemetry

- endpoint 仍是 `/api/event_logging/v2/batch`，请求 UA 为 `claude-code/2.1.260`。
- `env.version/version_base=2.1.260`，`build_time=2026-09-03T19:41:35Z`，
  `node_version=v26.3.0`。
- batch body 仍只有 `events`；常规 `event_data` 字段顺序与 2.1.257 相同，
  `skill_name` 仍是按事件可选字段，未观察到新 telemetry shape。
- `tengu_api_query` / `tengu_api_success` 的 `betas` 反映最终请求画像，包括 2.1.260
  新增的 display/per-turn token。
- 大量普通内部事件继续使用较窄的启动 beta，并保留
  `redact-thinking-2026-02-12`；它与主 `/v1/messages` beta 不是同一个常量。升级时
  不能因为 message beta 去掉 redact 就把 telemetry base beta 同步替换。
- 非 Opus 捕获在模型解析前会有少量默认 `claude-opus-5[1m]` telemetry，随后才变为
  Sonnet/Fable/Haiku；这不是 wire 主模型漂移。
- `flags=model` 和 `cli_flag=<页面选择>` 只出现在显式 model override 启动事件；继续
  保持“有覆盖才写”，不能按模型类型硬编码。

## 零首字节请求

Opus 和两份 Fable 5.1 raw flow 各有同一正文的两次未完成尝试：

| run | 模型 | messages | headers 等待 | 第一次到重试 | response | request ID |
| --- | --- | ---: | --- | ---: | --- | --- |
| `12a15859fced` | Opus 5 | 101 | 1.050-1.097s | 192.558s | 200，0 bytes | 两个不同 ID |
| `8b6129adc9fa` | Fable 5.1 | 20 | 2.785-5.728s | 186.626s | 200，0 bytes | 两个不同 ID |
| `aed307de9913` | Fable 5.1 | 47 | 1.190-1.446s | 190.583s | 200，0 bytes | 两个不同 ID |

6/6 请求的 `cc_version` 和 CCH 都命中对应 2.1.260 规则；每个 run 的 telemetry 都有
一次 `tengu_api_no_response_timeout` 和一次 `tengu_api_retry`。这与 2.1.257 已观察的
上游首字节卡死同类，不能归因于 beta、CCH 或 HTTP 拒绝。协议子任务只需保留既有
首字节/idle timeout 可观测性，不应通过伪造 SSE、放宽 hash 或无限延长超时处理。

## cc2api 实施清单

### 必须修改

1. `src/service/version_profile.rs`
   - 新增独立 2.1.260 profile、build time 和 `2.1.89-2.1.260` 默认允许范围。
   - 新增 2.1.260 通用、Fable 5.1、Haiku main/无 diagnostics beta。
   - 让非 Fable main 和 Haiku main 也能声明 `thinking.display=updates`，不能只在
     `FableRequestProfile` 中表达 display。
   - 把 CCH fallback 参与规则放到精确模型画像，修复 2.1.257 Fable 5 与 Fable 5.1。
   - bootstrap cwk 改为精确模型映射，增加 Sonnet 5=`pewter`。
2. `src/service/rewriter.rs`
   - 将 2.1.260 纳入 2156 CCH seed 和画像驱动的字节级归一化。
   - API mimicry 按 2.1.260 profile 补 display，保留已存在 thinking 字段，且字段插入
     顺序与抓包一致。
   - 主请求 beta 使用新 profile；Haiku probe/title/non-stream aux 保持旧窄画像。
   - 修复 2.1.257 Fable 5 的 fallback、beta 和 CCH，不再仅对 Fable 5.1 保留 fallback。
3. `src/service/gateway.rs`
   - configured/hide bootstrap 按精确模型处理 `marigold`、`sorrel`、`belladonna`、
     `pewter`，避免 Fable family 前缀合并。
4. `src/service/telemetry.rs`
   - 默认 env/UA 切到 2.1.260；保留 `ClaudeCode2185` shape。
   - 将启动/base beta 与最终 message beta 解耦，request 事件继续允许显式 betas 覆盖。
5. `src/store/settings_store.rs`、`src/store/db.rs`、`src/handler/router.rs`、
   `web/src/components/Settings.vue`
   - 默认 profile/range 从 2.1.257 迁移到 2.1.260，管理员自定义 range 继续保留。
   - 账号 canonical env 迁移 version/version_base/build_time；Stainless/Node 值不变。
6. `src/service/oauth.rs`、session hello/token tester 相关代码
   - 版本 UA 更新为 2.1.260；Bun 仍为 1.4.1，不新建无意义回滚常量。
7. README、示例配置和测试
   - 同步默认版本/range；加入人工 fixture 的 `cc_version`/CCH、四类模型 beta、display、
     Fable fallback、bootstrap cwk 与旧 profile 回滚断言。

### 不应修改

- `X-Stainless-Package-Version=0.112.1`
- `X-Stainless-Runtime=node`、`X-Stainless-Runtime-Version=v26.3.0`
- `Bun/1.4.1`
- `/api/hello`、eval、event logging、triggers、MCP 和 session endpoint 路由形态
- message 顶层字段顺序
- `cc_version` salt/索引算法、CCH seed
- 既有首字节 timeout 与首 chunk 前不注入 keepalive 的边界

## 证据不足

- 没有 2.1.260 `claude-fable-5` 主请求，不能确认它是否继承 Fable 5.1 的
  per-turn/display 行为。
- Sonnet 只有 2 条完成主请求，足以建立当前精确画像，但不足以覆盖长会话、无
  diagnostics 和异常重试变体。
- 没有 2.1.260 Fable 5.1 `[1m]` 入口样本，继续保留 2.1.257 的“不自动注入 1M”
  结论，但本轮不能宣称重新验证。
- `x-cc-atis` 只在一份旧 Opus 账号样本出现，不能归类为 2.1.260 的确定删除项。
- 大型 system 指令正文只做长度/hash 比较，不提交也不反向重建；身份块本身已确认不变。

## 结论

2.1.260 不是单纯版本号升级。确定变化包括：默认 identity/build time、Opus/Sonnet/
Haiku 的 thinking display 与主 beta、Fable 5.1 的 per-turn beta，以及 Sonnet bootstrap
`pewter`。确定不变的是 Stainless/Node/Bun、endpoint/header/body 顺序、telemetry
shape、`cc_version` 算法和 CCH seed。

同时，本轮基线回查发现 cc2api 的 2.1.257 Fable 5 fallback、fallback beta、CCH 和
bootstrap cwk 已与真实抓包不一致。协议子任务应把该历史漂移与 2.1.260 profile 一起
修复，之后再进入部署任务。
