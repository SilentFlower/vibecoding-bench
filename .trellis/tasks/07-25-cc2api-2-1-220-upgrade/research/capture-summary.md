# Claude Code 2.1.220 抓包摘要

## Sources

- Opus 5：`data/flows/7-24/7788/1512e30eb37c`
- Fable 5：`data/flows/7-24/7790/a0f3cfd653ea`
- 旧 Fable run `data/flows/7-12/7789/caa28dcdb85f` 已废弃，不作为验收依据。

完整抓包位于 gitignored `data/`，本文件只保留脱敏协议结论。

## Identity

```text
version=2.1.220
version_base=2.1.220
build_time=2026-07-24T22:17:45Z
node_version=v26.3.0
stainless_package_version=0.94.0
growthbook_user_agent=Bun/1.4.0
```

## Messages

- Opus 5 主请求模型：`claude-opus-5`。
- Fable 5 主请求模型：`claude-fable-5`，15/15 带 `fallbacks:[{"model":"claude-opus-5"}]`。
- Opus 5 与 Fable 5 主请求均观察到 `messages[].role=system`。
- Fable 15/15 `max_tokens=64000`，thinking 使用 `type`，并带 context management 与 effort output config。
- Fable body order：`model,messages,system,tools,metadata,max_tokens,thinking,context_management,fallbacks,output_config,diagnostics,stream`；1 条无 diagnostics，其余顺序一致。

Opus 5 无 1M 必需 beta：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

Fable beta：

```text
claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,redact-thinking-2026-02-12,thinking-token-count-2026-05-13,context-management-2025-06-27,prompt-caching-scope-2026-01-05,mid-conversation-system-2026-04-07,advisor-tool-2026-03-01,advanced-tool-use-2025-11-20,effort-2025-11-24,server-side-fallback-2026-06-01,fallback-credit-2026-06-01,extended-cache-ttl-2025-04-11,cache-diagnosis-2026-04-07
```

## Billing

- Opus `.flow`：51 个带 billing 的 message 样本，`cc_version` 51/51、CCH 51/51 命中。
- Fable `.flow`：18 个带 billing 的 message 样本，`cc_version` 18/18、CCH 18/18 命中。
- 合计 69/69 使用现有 `cc_version` 算法。
- CCH seed：`0x4D659218E32A3268`。
- CCH input：顶层 `model` 置空，删除顶层 `max_tokens` 和 `fallbacks`；保留 diagnostics 和嵌套同名字段。

## Bootstrap And Endpoints

- Opus bootstrap query model 为 `claude-opus-5`，响应 `cwk_cfg_key=belladonna`。
- Fable bootstrap query model 为 `claude-fable-5`，响应 `cwk_cfg_key=marigold`。
- 两者均包含 `client_data.cedar_basin="2026-08-31"`、Fable/Mythos cedar lagoon 开关和 `claude-fable-5[1m]` additional model option。
- `HEAD /api/hello` 为启动第一跳，无鉴权、空 body、返回 200；GET 真实 body 为 `{"message": "hello"}`。
- OAuth、triggers、MCP servers、Haiku title/probe 的 beta/协议未观察到需要新增 shape 的变化。

## Telemetry

- Opus run 63 个 event logging batch；Fable run 27 个 batch。
- 2.1.220 event_data 顶层字段集合和 env 字段集合与现有 `ClaudeCode2185` 相同。
- 原生事件包含非空 `skill_name`，现有 in-place rewrite 可保留。
- 模型和 betas 随最终请求变化；Fable CLI flag 只在显式 model flag 事件出现，不能按模型无条件合成。
- 新增或变化的客户端本地事件名不要求服务端自动 telemetry 全量复制。

## Unchanged Evidence

- `currentDate` 使用 ASCII apostrophe 和 `-` 日期分隔符，无需修改风险治理规则。
- Stainless package、Node runtime、GrowthBook UA 和 telemetry wire shape 均可复用现有结构。
