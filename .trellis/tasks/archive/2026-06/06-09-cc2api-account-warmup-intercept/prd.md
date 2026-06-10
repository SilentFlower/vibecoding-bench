# brainstorm: cc2api 账号级预热请求拦截

## Goal

在 `/root/project/cc2api` 中增加全局“预热/探测请求拦截”能力，模仿 `/root/project/sub2api` 的本地 mock 响应实现，用于拦截 Claude Code / Claude 类客户端发出的标题生成、Suggestion Mode、Haiku 连通性探测等低价值请求，避免消耗上游 token 和连接资源。

用户最初提到“账号级别”，随后调整为“全局配置”，但要求控制粒度更细：不是单一总开关，而是能分别控制不同预热/探测请求类型。

## Background / Known Context

- sub2api 的实现位于 `/root/project/sub2api/backend/internal/handler/gateway_handler.go`：
  - 账号 credentials 中的 `intercept_warmup_requests=true` 才启用。
  - 命中后在转发上游前直接返回 mock 响应。
  - 识别类型包括：
    - `SUGGESTION MODE`：最后一条 user 消息文本以 `[SUGGESTION MODE:` 开头，mock 空字符串。
    - 标题/预热请求：消息中包含 `Please write a 5-10 word title for the following conversation:`、文本正好是 `Warmup`，或 system 中包含 `extract a 2-3 word title` 相关提示，mock `New Conversation`。
    - Haiku 探测：Claude Code 客户端、非流式、模型名包含 `haiku`、`max_tokens=1`，mock `#`，`stop_reason=max_tokens`。
- 已用 `data/flows` 中两组实际抓包对比：
  - 样本路径：
    - `data/flows/auto-2/1887/46ba25a8d791/http_capture.jsonl`
    - `data/flows/pingguo-1/2873/10f2065adf44/http_capture.jsonl`
  - 共 43 条 `POST /v1/messages?beta=true` 请求，全部 200。
  - 命中高置信辅助请求 6 条：
    - Haiku `max_tokens=1` 非流式 quota 探测：2 条，真实输出 `#`。
    - `SUGGESTION MODE`：2 条，真实输出短建议文本。
    - 新版 Claude Code 标题生成：2 条，旧 sub2api 标题规则没有覆盖。
  - 旧 sub2api 标题规则在这两组抓包中 0 命中，但应保留用于兼容旧客户端。
  - 新版标题生成的 system prompt 包含 `Generate a concise, sentence-case title (3-7 words) that captures the main topic or goal of this coding session`，并通过 `output_config.format.type=json_schema` 要求返回 `{"title": "..."}` 形态的文本。
  - 不能使用泛化 `title` 关键词拦截；普通真实对话和 assistant 输出可能包含标题类文本，泛化匹配有误拦截风险。
- cc2api 目前已有全局 settings 体系和设置页，例如 `proxy_client_pool_enabled`、`cache_control_ttl_rewrite`。
- cc2api 主网关在 `GatewayService::handle_request_inner` 中已读取请求体、识别 client type、选择账号、获取 RPM/并发槽位、改写并转发上游。
- 本功能应尽量在进入上游前完成，不应触发真实上游请求。

## Requirements

- 提供全局预热拦截配置，不新增账号级字段。
- 配置粒度至少拆分为三类：
  - 标题/`Warmup` 预热请求拦截。
  - `SUGGESTION MODE` 请求拦截。
  - Claude Code Haiku `max_tokens=1` 非流式探测请求拦截。
- 命中拦截时返回符合 Anthropic `/v1/messages` 响应结构的 mock 响应。
- 支持流式和非流式响应；流式请求返回 SSE 事件，非流式请求返回 JSON。
- 拦截发生在上游转发前，且不应调用 `resolve_upstream_token` 或发起上游 HTTP 请求。
- 设置页需要能查看和修改这些全局开关。
- 三类全局开关默认全部关闭，避免上线后突然改变所有请求行为；由管理员在设置页逐项开启。
- 标题预热拦截需要同时覆盖旧 sub2api 文本标题模式和新版 Claude Code JSON 标题模式；二者共用一个标题拦截开关。
- 新版 Claude Code JSON 标题模式命中时，mock content 必须是 JSON 文本，例如 `{"title":"New Conversation"}`，不能返回裸文本 `New Conversation`。

## Acceptance Criteria

- [ ] `/admin/settings` 返回并保存预热拦截全局配置。
- [ ] 设置页可分别开启/关闭标题预热、Suggestion Mode、Haiku 探测三类拦截。
- [ ] 命中标题/`Warmup` 预热请求时，返回 mock 文本 `New Conversation`。
- [ ] 命中新版 Claude Code JSON 标题请求时，返回 mock 文本 `{"title":"New Conversation"}`。
- [ ] 命中 `SUGGESTION MODE` 请求时，返回空文本 mock。
- [ ] 命中 Haiku `max_tokens=1` 非流式探测时，返回 `#` 且 `stop_reason=max_tokens`。
- [ ] 未开启对应子规则时，请求保持现有转发行为。
- [ ] 非 `/v1/messages` 请求不受影响。
- [ ] 增加单元测试覆盖识别规则和 mock 响应关键字段。
- [ ] `cargo test`、`npm --prefix web run build`、`cargo fmt --check` 通过。

## Decisions

- 三类子规则默认全部关闭。
- 结合 `data/flows`，仅靠 sub2api 旧标题规则不够；需要补充新版 Claude Code 标题 system prompt 规则。
- 当前样本中补充新版标题规则后，三类开关覆盖了全部高置信预热/辅助请求；暂不加入泛化关键词规则。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
