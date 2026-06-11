# cc2api assistant prefill 拦截与 429 请求观测

## Goal

为 cc2api 增加两个默认关闭的全局治理能力:一是在不支持 assistant prefill 的模型上,在请求进入账号选择/RPM/并发/上游转发前本地拦截最后一条 `messages[].role=assistant` 的 `/v1/messages` 请求,避免已知 400/潜在风暴继续消耗账号池;二是在上游返回 429 时,可按配置记录脱敏、截断后的实际上游请求头和请求体,帮助定位近期非流式请求风暴特征。

## Background / Known Context

* 远程近期 400 包含 `This model does not support assistant message prefill. The conversation must end with a user message.`。
* Anthropic Messages API 允许历史 assistant 消息,但最后一条 assistant 消息会被解释为 assistant prefill;部分新模型明确不支持 prefill。
* 用户希望 assistant prefill 先做成全局配置直接拦截。
* 用户希望 429 请求观测也纳入同一任务,同样做成全局配置。
* cc2api 已有全局设置链路:`settings` 表默认值、`/admin/settings` GET/PUT、`GatewayService` 内存 `RwLock` 缓存、`Settings.vue` 设置页。
* 429 观测必须避免泄露 Authorization、Cookie、API key、token、password、secret 等敏感值。

## Requirements

* 增加全局配置 `intercept_assistant_prefill_enabled`,默认 `false`。
* 增加全局配置 `intercept_assistant_prefill_models`,保存逗号分隔模型 ID 列表;默认值为 `claude-fable-5,claude-opus-4-8,claude-opus-4-7`。
* 当配置开启且请求满足 `/v1/messages`、模型命中列表、`messages` 最后一条 role 为 `assistant` 时,本地返回 400,不进入账号选择、RPM、并发槽和上游转发。
* assistant prefill 拦截响应应使用 JSON 错误体,包含稳定错误 code,便于客户端和日志识别。
* 增加全局配置 `log_429_request_enabled`,默认 `false`。
* 增加全局配置 `log_429_request_body_limit`,控制 429 请求体日志最大字符数。
* 当上游返回 429 且观测开关开启时,日志记录实际上游请求的路径、账号、模型、stream、请求头和请求体摘要/截断内容。
* 429 观测日志必须脱敏敏感请求头和 JSON 请求体敏感字段,并截断过长内容。
* 设置页需要能查看/修改上述全局配置。
* 配置保存后应热加载,不要求重启服务。

## Acceptance Criteria

* [ ] 默认情况下 assistant prefill 拦截和 429 请求体观测都关闭,升级后不改变现有请求行为。
* [ ] 开启 assistant prefill 拦截后,命中配置模型且最后一条消息为 assistant 的 `/v1/messages` 请求直接返回本地 400。
* [ ] 未命中模型、最后一条不是 assistant、非 `/v1/messages`、配置关闭时不触发 assistant prefill 拦截。
* [ ] 429 观测开启后,上游返回 429 时日志包含固定标记、账号、路径、模型、stream、脱敏请求头和截断后的脱敏请求体。
* [ ] 429 观测日志不包含 Authorization、Cookie、x-api-key、anthropic-api-key、access_token、refresh_token、password、secret 等敏感值原文。
* [ ] `/admin/settings` GET 返回新配置默认值,PUT 校验布尔、模型列表和 body limit 后保存。
* [ ] 设置页可配置新功能,非法输入会阻止保存。
* [ ] Rust 单测覆盖 assistant prefill 检测、模型列表匹配、429 脱敏和截断。
* [ ] 通过 `cargo fmt`、相关 Rust 测试、前端 build 和 `git diff --check`。

## Out of Scope

* 不在本任务中把 429 观测写入数据库或新增日志查询页面。
* 不在本任务中自动拦截所有非流式请求。
* 不在本任务中基于 429 观测结果自动调整账号调度策略。
* 不在本任务中强制修改客户端请求体为 user 结尾。
* 不默认覆盖所有官方不支持 assistant prefill 的模型集合;本任务先使用当前事故相关模型列表,后续可通过设置页扩展。

## Decision (ADR-lite)

**Context**: assistant prefill 拦截范围过大会带来误拦截风险,范围过小则需要后续手动补模型。

**Decision**: 默认模型列表采用当前事故相关集合: `claude-fable-5,claude-opus-4-8,claude-opus-4-7`;总开关仍默认关闭。

**Consequences**: 升级后不会改变默认行为;管理员开启后只拦截当前已关注模型,后续发现新模型可通过设置页扩展列表。

## Research References

* Anthropic Messages API 文档: assistant prefill 是最后一条 assistant 消息的语义。
* Anthropic 模型迁移/兼容说明:部分新模型不支持 assistant prefill。
