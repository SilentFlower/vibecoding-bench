# Claude Code 2.1.257 Fable 5.1 抓包摘要

## Sources

- 目标 Fable 5.1：`data/flows/7-24/9591/9333aa5d1fe3`
- 多轮与超时复现：`data/flows/7-24/9601/724f47b5673c`
- `[1m]` 入口解析与二次超时复现：`data/flows/7-12/9603/86926719c1ee`
- 2.1.220 Fable 5 基线：`data/flows/7-24/7790/a0f3cfd653ea`

完整抓包位于 gitignored `data/`，本文件只保留脱敏协议结论。

## Hash Verification

目标抓包包含 4 条 `/v1/messages`，其中 3 条有 billing header：2 条相同的 Haiku
title 请求和 1 条 Fable 5.1 主请求。

| 验证项 | 结果 |
| --- | --- |
| `cc_version` 旧 SHA256 文本索引算法 | 3/3 命中；Fable 5.1 为 `2.1.257.e73` |
| 当前未知版本路径：legacy seed + 完整 body | 0/3 命中 |
| 2.1.220 CCH 规则：2156 seed + 去 `model/max_tokens/fallbacks` | Haiku 2/2，Fable 5.1 0/1 |
| 2.1.257 正确规则：2156 seed + 去 `model/max_tokens`、保留 `fallbacks` | 3/3 命中 |

结论：

- `cc_version` 后缀算法不变，仍取首条 user message 的最后一个 text block，并按
  JavaScript UTF-16 索引语义计算 SHA256 前 3 位。
- CCH seed 不变，仍为 `0x4D659218E32A3268`。
- Fable 5.1 的 CCH 输入规则发生变化：顶层 `fallbacks: "default"` 必须保留并参与
  hash。不能直接把 2.1.257 加进当前 2172+ 的“删除 fallbacks”版本列表。
- 当前 `BillingProfile.cch_profile` / `cc_version_algorithm` 只在画像中声明，实际
  `rewriter` 仍按版本字符串硬编码分支。新增 profile 本身不会让 CCH 命中。
- 新样本的原始 `.flow` 包含 4 条 Fable 5.1 请求：2 条成功请求，以及同一第三轮请求
  的首次尝试和重试。4/4 的 `cc_version` 均命中，4/4 的 CCH 均只在保留
  `fallbacks: "default"` 时命中，覆盖了多轮 tool continuation。

## Fable 5.1 Message Profile

| 字段 | 2.1.220 Fable 5 | 2.1.257 Fable 5.1 |
| --- | --- | --- |
| model | `claude-fable-5` | `claude-fable-5-1` |
| max_tokens | `64000` | `64000` |
| fallbacks | `[{"model":"claude-opus-5"}]` | `"default"` |
| thinking | `{"type":"adaptive"}` | `{"type":"adaptive","display":"updates"}` |
| body order | Fable 2.1.220 order | 相同顺序 |
| context_management | `clear_thinking_20251015 / keep=all` | 不变 |
| output_config | `effort=max` | 不变 |
| diagnostics | `previous_message_id` | 不变 |

Fable 5.1 主请求 beta：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-07-01,fallback-credit-2026-06-01,thinking-display-updates-2026-08-18,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

相对 2.1.220：

- 移除 `redact-thinking-2026-02-12`。
- `server-side-fallback-2026-06-01` 升级为
  `server-side-fallback-2026-07-01`。
- 新增 `thinking-display-updates-2026-08-18`。

## Bootstrap And Identity

- bootstrap query：`model=claude-fable-5-1`。
- `additional_model_options`：`claude-fable-5-1[1m]`。
- `cwk_cfg_key`：`marigold` 变为 `sorrel`。
- `client_data.cedar_basin`：`2026-08-31` 变为 `2027-08-31`。
- `client_data.cedar_lagoon` 的 Fable/Mythos 开关不变。
- bootstrap response 使用 `Content-Encoding: br`；现有 gateway 已支持 Brotli 解码，
  无需新增解压算法。
- Stainless package：`0.94.0` 变为 `0.112.1`。
- Node runtime：仍为 `v26.3.0`。
- GrowthBook / hello UA：`Bun/1.4.0` 变为 `Bun/1.4.1`。
- build time：`2026-09-01T05:28:54Z`。

旧 profile 必须继续保留 `0.94.0` / `Bun/1.4.0`，不能通过修改共享常量破坏
2.1.220 回滚画像。

## Haiku Observation

- Haiku 独立样本 `ea6d8e9bb665` 已完成复核，结论见
  `research/haiku-capture-summary.md`。
- probe/title beta 常量可保留，但新 title 必须通过结构识别；Haiku 主请求和
  `max_tokens=1024` 辅助请求需要 2.1.257 子画像。

## `No response from API` 复现结论

新样本不是所有 Fable 5.1 请求都失败：前两轮主请求均收到 HTTP 200、完整 SSE
`message_stop`，并以 `tool_use` 正常结束。第三轮 8-message 请求连续两次失败：

| 尝试 | 请求体 | HTTP headers | SSE body | 客户端行为 |
| --- | --- | --- | --- | --- |
| 首次 | 107592 bytes，Fable 5.1 正确 beta / CCH / fallback | 约 3.33 秒后收到 200 | 180.67 秒内 0 bytes | 请求开始 184 秒后主动断开 |
| 重试 | 与首次请求完全相同 | 约 3.26 秒后收到 200 | 180.74 秒内 0 bytes | 请求开始约 184 秒后主动断开 |

两次上游 request ID 分别为：

- `req_011Ceder5LQrfz3XDKoEJpT4`
- `req_011Cedf5gMBu75ZWU1MUAtki`

telemetry 与 raw flow 相互印证：

- 第 30 秒分别记录 `tengu_api_slow_first_byte`；
- 首次尝试在 184000 ms 记录 `tengu_api_no_response_timeout`；
- 随后记录 `tengu_api_retry`，错误为 `Connection error.`；
- 两次 raw flow 都已收到 HTTP 200 和 request ID，但没有任何 `message_start`、
  `ping` 或其他 SSE 字节，最终由客户端断开；
- Claude Code 随后生成 `<synthetic>` assistant 消息，`error=server_error`，文本为
  `API Error: No response from API`。

因此该报错不是 4xx/5xx、CCH 不命中、beta 被拒绝或 SSE 解析失败，而是上游接受
请求后一直没有发送首个 SSE body chunk。失败请求与成功请求使用同一模型画像，且
失败请求的 `cc_version` / CCH 均可复算命中。

线上 cc2api 当前 `stream_upstream_idle_timeout_secs=120`，并且实现明确不会在收到
第一个上游 chunk 之前注入 keepalive。相同上游故障经 cc2api 转发时会在约 120 秒
先被网关关闭；keepalive 配置不能修复“首字节为零”的上游卡死。

## `[1m]` 入口解析结论

用户确认 run `86926719c1ee` 是通过 Fable 5.1 `[1m]` 入口发起。该抓包直连
`api.anthropic.com`，可以排除 cc2api 在链路中改写 beta：

- 启动 telemetry 在 `2026-09-02T01:12:11Z` 先记录模型
  `claude-opus-5[1m]`，其 beta 包含 `context-1m-2025-08-07`；
- 约 1.3 秒后，启动模型解析完成，telemetry、bootstrap query 和后续会话模型均变为
  `claude-fable-5-1`，beta 不再包含 `context-1m-2025-08-07`；
- 两条成功的 Fable 5.1 主请求均使用标准 Fable 5.1 beta，没有 1M token，body 中模型
  也是 `claude-fable-5-1`，而不是带 `[1m]` 的模型 ID；
- stats 还记录了两条没有 response 事件的 Fable 5.1 请求。第一次在约 184 秒后触发
  `tengu_api_no_response_timeout` 并重试，第二次重试到抓包结束仍无 response；对应
  telemetry 同样不含 1M beta。

因此，2.1.257 在这条官方链路上的可观察行为是：`[1m]` 入口经过模型解析后落到
Fable 5.1 标准请求，并由 Claude Code 自身不再携带 1M beta。不能把 bootstrap 广告的
`claude-fable-5-1[1m]` 直接解释为 message 请求必须注入 `context-1m`。

当前 cc2api 还有独立的账号能力过滤：线上账号 `allow_1m_models` 不含 `fable`，所以
即使未来客户端显式传入 `context-1m-2025-08-07`，网关也会将其剥离。两层行为需要
区分：本抓包中的 1M token 消失发生在 Claude Code 直连阶段，不是 cc2api 所致；而
cc2api 当前默认策略也不会为 Fable 5.1 保留该 token。

本轮升级不自动迁移账号 `allow_1m_models`、不为 Fable 5.1 注入 1M beta。待后续抓包
证明官方实际 message 请求会携带 `context-1m` 后，再单独评估账号放行策略。

该结论也进一步排除了 1M beta 与 no-response 的因果关系：成功请求与首字节卡死请求
使用同一套无 1M 的 Fable 5.1 wire profile。

## New Endpoint Observations

2.1.257 抓包新增以下官方 API 流量：

- `/v1/ultrareview/quota`：Claude CLI UA，无 beta。
- `/api/claude_code/notification/preferences`：Claude CLI UA，OAuth beta，无
  `Content-Type`。
- `/v1/code/sessions...` / `/v1/sessions...`：主要使用 Claude Code UA，无 beta；
  `client/presence` 使用 axios UA。

当前通用改写会：

- 给 `/v1/ultrareview/quota` 和 code session 路径错误注入 message beta。
- 给 notification preferences 注入完整 message beta，并补不存在的 Content-Type。
- 把多数 code session 请求改成 Claude CLI UA。

这些 endpoint 是否遵循 `ANTHROPIC_BASE_URL` 尚未通过目标版本探针确认。实现前应先
验证路由来源；若固定官方域名，则不应仅因抓包出现就扩展 cc2api 转发画像。

## Existing Code Impact

- `rewriter::is_fable_model` 只精确匹配 `claude-fable-5`，会导致 Fable 5.1 使用错误
  beta、错误 max_tokens、缺失 fallbacks，并落入错误 body order。
- `account::is_fable_quota_model_id` 只识别 Fable 5，Fable 5.1 不会进入周额度保护。
- `allow_system_role_models` 默认值不含 `claude-fable-5-1`；目标主请求包含
  `messages[].role=system`，当前会被网关本地拒绝。
- bootstrap query 的 prefix 判断已识别 Fable 5.1，但 configured 模式的默认 option、
  `sorrel`、cedar basin 和旧默认 settings 迁移仍需同步。
- session hello probe 的 UA 仍硬编码 `Bun/1.4.0`。
- telemetry 顶层/event_data/env shape 不变；新增 `cc_prompt_id` 等
  `additional_metadata` 字段可由现有透传逻辑保留，不需要新 telemetry shape。

线上精确设置和代码匹配审计见
`research/fable-5-1-online-compatibility-audit.md`。
