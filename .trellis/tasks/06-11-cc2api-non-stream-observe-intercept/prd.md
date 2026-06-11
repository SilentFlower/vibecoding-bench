# cc2api 非流请求观测与拦截

## Goal

在 `/root/project/cc2api` 中增强 429 请求观测里的非流 `/v1/messages` 可观测性，并把已经确认的 Claude Code 非流辅助轮询请求纳入“预热请求拦截”体系，减少这类短输出、大上下文请求对上游 token、连接和账号并发的消耗。

## Background / Known Context

- 当前 429 请求观测已有两个开关：`log_429_request_enabled` 和 `log_non_stream_request_enabled`，并共用 `log_429_request_body_limit` 作为请求体日志字符上限。
- 当前非流请求日志只在上游转发前打印最终上游请求头和请求体，不打印上游返回内容。
- 远程观测到的 `non_stream_request_capture` 主体特征：`/v1/messages`、`stream=false`、多数 `max_tokens=64`、`X-Stainless-Retry-Count=0`、`claude-cli/2.1.172`、多数带 `context-1m-2025-08-07`，请求体约 `57KB..183KB`，多个 Claude Code session 反复出现。
- 最新 3 小时样本中，非流请求并非全部 `max_tokens=64`：53 条里 `64` 为 51 条，另有 `64000` 和 `8192` 各 1 条；初始拦截只覆盖 `max_tokens=64` 的高置信辅助轮询子类，其它非流请求先观测不拦截。
- 最新 3 小时样本中的 400 均为上游 `/v1/messages` 返回的 `prompt is too long: ... > 1000000 maximum`，集中在 account 14；newapi 侧实际展示成 500，但 429（例如 `status_code=429, too many requests: sticky account rpm limit reached`）能正常显示，说明问题更可能在非 429 上游错误的透传链路、响应头或外层包装，而不是 newapi 无法处理所有错误格式。
- 这类请求不像主回答流式请求，更像 Claude Code 的短输出辅助请求/状态分析/小结类轮询。
- 现有“预热请求拦截”已支持标题/Warmup、Suggestion Mode、Haiku 探测，命中后本地返回 mock 响应，不转发上游。
- Settings 页目前已有“预热请求拦截”和“429 请求观测”卡片，适合新增相关配置入口。
- 相关前置小修：请求体字符上限输入应允许填 `64000` 这类任意合法整数，前端 `step=1024` 与后端校验不一致。

## Requirements

- 非流 `/v1/messages` 观测在开启 `log_non_stream_request_enabled` 时，除请求头和请求体外，还要记录上游返回的输出内容摘要。
- 非流返回日志必须脱敏并截断，不能输出 Authorization、Cookie、token、password、secret 等敏感内容。
- 非流返回日志的截断上限优先复用现有“请求体字符上限”，避免新增过多相近配置。
- 非流返回日志必须只作用于非流 `/v1/messages`，不改变流式响应语义。
- 新增一类“非流辅助请求”拦截，归入预热请求拦截设置区域。
- 非流辅助请求拦截必须默认关闭，避免升级后改变现有转发行为。
- 非流辅助请求命中特征至少覆盖当前高置信形态：Claude Code 客户端、`/v1/messages`、`stream=false`、`max_tokens=64`、较大请求体/多 text block、非 Haiku 探测、非标题、非 Suggestion Mode。
- 非流辅助请求初始拦截不得把 `model` 固定为 Opus 系列；模型只做日志字段或可选配置项，避免未来 Fable / 其它 Claude Code 模型漏判。
- 命中拦截时不进入上游转发，避免消耗上游请求、账号并发和 token。
- 拦截响应模式可配置，至少支持“返回固定 assistant 文本”和“返回错误”。
- 非流辅助请求拦截的默认响应模式为“返回固定 assistant 文本”，使用 HTTP 200，避免 Claude Code 把本地拦截直接显示为请求错误。
- Settings 页要能配置非流辅助请求拦截开关和响应模式，并展示简短说明。
- 日志必须能区分非流请求转发观测、非流返回观测和非流辅助请求拦截命中。
- 对上游 `/v1/messages` 非 429 错误响应，日志必须记录返回给下游前的安全摘要：HTTP status、content-type、content-encoding、content-length、transfer-encoding、body_summary、可提取的 `error.message`。
- 若确认 400 因响应头与已缓冲 body 不一致、压缩/长度头残留、或外层包装导致 newapi 变成 500，应修复透传响应构建；默认不把所有 API 错误体改写成另一套格式。

## Acceptance Criteria

- [ ] 开启非流请求日志后，真实非流 `/v1/messages` 上游返回 200 时，日志包含脱敏/截断后的响应摘要和响应体内容。
- [ ] 非流响应日志不泄露 Authorization、Cookie、token、password、secret 等敏感字段或明文 bearer token。
- [ ] 非流响应日志不影响客户端收到的原始 HTTP status、headers 和 body。
- [ ] 开启“非流辅助请求拦截”后，符合 `stream=false + max_tokens=64 + Claude Code + 当前辅助请求特征` 的请求本地返回，不再转发上游。
- [ ] “非流辅助请求拦截”关闭时，这类请求仍正常转发上游。
- [ ] 响应模式为固定文本时，返回 Anthropic `/v1/messages` 兼容的 message JSON，文本可被客户端安全消费。
- [ ] 响应模式为错误时，返回 Anthropic/OpenAI 可解析的标准 error 对象。
- [ ] Settings 页保存后能热刷新配置，无需重启容器。
- [ ] 历史数据库实例迁移后新增设置项有默认值。
- [ ] Rust 单测覆盖检测规则、mock 响应、错误响应、响应日志脱敏与截断。
- [ ] 前端构建通过，Settings 页能保存 `64000` 请求体字符上限。
- [ ] 上游 `prompt is too long` 400 的非流响应日志能显示实际返回下游前的 status、关键响应头、body 摘要和 `error.message`。
- [ ] 若 400 透传响应需要重建，返回给 newapi 的 HTTP status 仍为 400，body 中保留可解析的 `error.message`，且不会因响应头/body 不一致被 newapi 显示成 500。

## Definition of Done

- `cargo fmt --check`
- `cargo test`
- `npm run build` in `/root/project/cc2api/web`
- 远程或本地手动验证：开启日志后能看到非流响应摘要；开启拦截后对应请求不打到上游。
- 部署前通过 `trellis-check-all`。

## Out of Scope

- 不实现通用 prompt 内容分类器。
- 不修改 Claude Code bootstrap 是否走代理的问题。
- 不改变普通流式 `/v1/messages` 转发和响应行为。
- 不默认开启新拦截策略。
- 不记录完整未截断 prompt 或响应正文到日志。

## Decisions

- 非流辅助请求拦截命中后的默认响应模式选择“固定 assistant 文本”。错误对象仍保留为可选模式，用于后续排查或强提示场景。

## Research References

- 远程日志观测：`non_stream_request_capture` 最新 3 小时样本显示 53 条，`stream=false`、`claude-cli/2.1.172`、`X-Stainless-Retry-Count=0` 稳定；`max_tokens=64` 为主体，但存在 `8192/64000` 例外，需要先观测。
- 远程观测：本地 429 错误（如 `sticky account rpm limit reached`）可在 newapi 正常显示；400 问题需要针对非 429 上游错误透传链路排查。
