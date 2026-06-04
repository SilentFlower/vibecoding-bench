# cc2api Claude Code 2.1.156 遥测事件画像优化

## Goal

基于 `46ba25a8d791` 抓包中的真实 Claude Code `2.1.156` 遥测行为，升级 `/root/project/cc2api` 的自动遥测与遥测改写能力，让事件类型、字段结构、批量发送节奏和请求生命周期更接近真实客户端，而不是只发送固定的单一成功事件。

## Background / Known Context

- 抓包目录：`/root/project/vibecoding-bench/data/flows/auto-2/1887/46ba25a8d791/`。
- 抓包文件包括 `http_capture.jsonl`、`capture_index.json`、`stats.jsonl`、`20260604-024430.flow`。
- 安全摘要显示该 run 共 60 条 flow，host 全部为 `api.anthropic.com`。
- 其中 `/api/event_logging/v2/batch` 共 31 条，`/api/eval/sdk-zAZezfDKGoZuXXKe` 共 1 条。
- event logging 中包含约 506 个 `ClaudeCodeInternalEvent` 和 4 个 `GrowthbookExperimentEvent`。
- 抓包中高频事件包括 `tengu_feature_ok`、`tengu_api_cache_breakpoints`、`tengu_sysprompt_boundary_found`、`tengu_attachment_compute_duration`、`tengu_tool_search_mode_decision`、`tengu_api_before_normalize`、`tengu_api_after_normalize`、`tengu_sysprompt_block`、`tengu_api_query`、`tengu_api_success`、`tengu_skill_loaded`、`tengu_tool_use_success` 等。
- 当前 cc2api 的 [telemetry.rs](/root/project/cc2api/src/service/telemetry.rs) 自动代发主要覆盖固定的 `tengu_api_success` 和 GrowthBook eval，事件画像明显偏薄。
- 当前开启 `auto_telemetry` 后会拦截客户端 telemetry 请求并返回空成功；这能降低敏感数据外发风险，但也会让真实客户端事件链路被替换为 cc2api 的固定模板。

## Requirements

- 从抓包中建立安全的遥测事件目录，只记录 endpoint、事件名、字段名、字段类型、出现次数、批次大小和时间间隔摘要，不记录 token、prompt、请求体全文或响应体全文。
- 自动遥测从“固定定时模板”升级为“事件队列 + 批量发送”模型，至少能根据 `/v1/messages` 请求生命周期生成 API 查询、normalize、system prompt block、成功、慢首包/失败等事件。
- 事件模板至少覆盖抓包中已确认的关键类型：启动类、API 生命周期类、system prompt 边界/块、工具/权限类、技能加载类、文件/附件类、GrowthBook 实验类。
- 保留 `auto_telemetry` 的隐私边界：默认不把真实客户端 telemetry 原文透传到上游；代发事件只使用账号身份画像、请求摘要和安全派生字段。
- 改写真实客户端 telemetry 请求时，继续覆盖 `device_id`、`email`、`account_uuid`、`organization_uuid`、`env`、`process`、`additional_metadata`、`user_attributes` 等身份相关字段。
- 自动代发的 event batch 必须使用 `/api/event_logging/v2/batch`、`User-Agent=claude-code/2.1.156`、`anthropic-beta=oauth-2025-04-20`、`x-service-name=claude-code`。
- 事件节奏不能是完全固定心跳；应能与实际 `/v1/messages`、工具调用、错误/重试和 session 生命周期产生相关性。
- README 或任务研究记录需要说明遥测兼容范围、隐私策略、仍未覆盖的事件类型。

## Acceptance Criteria

- [ ] 任务内有一份安全遥测目录，列出 `46ba25a8d791` 中 event logging 的事件名、出现次数、字段集合和批次摘要。
- [ ] cc2api 自动遥测不再只发送单个固定 `tengu_api_success` 模板。
- [ ] `/v1/messages` 成功请求能驱动一组相关的 API 生命周期事件，并进入 v2 batch。
- [ ] GrowthBook eval attributes 与 2.1.156 抓包字段保持兼容。
- [ ] 真实客户端 telemetry 请求被拦截/改写时，不会泄露原始 token、prompt 或响应全文到日志和 git。
- [ ] 新增或更新测试，覆盖事件队列、v2 batch 构造、身份字段改写、关键事件模板和隐私边界。
- [ ] README 或内部文档更新，说明自动遥测事件画像的覆盖范围和限制。

## Out of Scope

- 不提交 `http_capture.jsonl`、`.flow`、token、prompt、响应体全文或账号敏感 profile。
- 不追求一次性 100% 复刻全部遥测事件；优先覆盖抓包中高频和与请求生命周期强相关的事件。
- 不处理账号运营策略、封禁规避策略或平台风控绕过策略。

## Research References

- 抓包目录：`data/flows/auto-2/1887/46ba25a8d791/`
- 父任务：`.trellis/tasks/06-04-cc2api-claude-code-2156-cch-upgrade`
- 目标代码：`/root/project/cc2api/src/service/telemetry.rs`、`/root/project/cc2api/src/service/rewriter.rs`、`/root/project/cc2api/src/service/gateway.rs`
