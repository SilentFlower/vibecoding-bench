# cc2api Auto Mode classifier 观测与拦截

## Goal

在 `/root/project/cc2api` 中保留非流 `/v1/messages` 响应观测能力，并先针对 Claude Code Auto Mode classifier 的 Stage 1 / Stage 2 side-query 做强特征识别与可控本地 mock，减少已确认的 classifier 请求对上游 token、连接和账号并发的消耗。

## Background / Known Context

- 当前 429 请求观测已有 `log_429_request_enabled`、`log_non_stream_request_enabled` 和共用的 `log_429_request_body_limit`。
- 已实现的非流响应缓冲日志会在重建下游响应前解码 gzip/br/zstd/deflate，并移除旧 `Content-Encoding`、`Content-Length`、`Transfer-Encoding`，避免已缓冲明文 body 仍带压缩头导致下游展示异常。
- `/root/project/claude-code/src/utils/permissions/yoloClassifier.ts` 显示 Auto Mode XML classifier 是两阶段 side-query：
  - Stage 1：`max_tokens=64 + thinkingPadding`，追加 `XML_S1_SUFFIX`，默认带 `stop_sequences=["</block>"]`。
  - Stage 2：`max_tokens=4096 + thinkingPadding`，追加 `XML_S2_SUFFIX`，无 `stop_sequences`。
  - 两阶段都走 `sideQuery()`，`temperature=0`，`skipSystemPromptPrefix=true`，user content 包 `<transcript>...</transcript>`。
  - allow 语义是 `<block>no</block>`；block 语义是 `<block>yes</block>`。
- 远程日志中 `max_tokens=64` 高频非流大 transcript 请求与 Stage 1 classifier 高度吻合。
- 远程日志中的 `8192` 不能只按数字归类；必须叠加 XML output format、transcript 结构等强特征。
- `max_tokens=64000` 结合 Claude Code `MAX_NON_STREAMING_TOKENS=64000`，更像 streaming watchdog / streaming failure 后的 non-streaming fallback，本轮不拦截。
- 这类 `64000` fallback 的优化方向是稳定流式连接，避免 Claude Code 字节级 watchdog 因长时间无新字节而触发 fallback；本轮通过可配置 SSE comment keep-alive 做低风险缓解。

## Requirements

- 保留并验证非流 `/v1/messages` 响应日志：开启 `log_non_stream_request_enabled` 后，记录上游返回摘要，并保持下游 status/body 可解析。
- 新增 Auto Mode classifier 处理策略，默认纯转发，必须显式开启 mock 才能本地返回。
- 分别支持 Stage 1 与 Stage 2 的独立模式配置：
  - `passthrough`：纯转发，不改变行为。
  - `mock_allow`：不请求上游，返回 Anthropic `/v1/messages` 兼容 message JSON，文本为 `<block>no</block>`。
  - `mock_block`：不请求上游，返回 message JSON，文本为 `<block>yes</block><reason>blocked by local policy</reason>`。
  - `error`：不请求上游，返回标准 error object。
- Stage 1 命中必须基于强特征：Claude Code 客户端、`/v1/messages`、非流、`max_tokens` 在 `64..2304`、最后一条消息为 `user`、请求文本包含完整 `<transcript>...</transcript>`，并包含 XML classifier 输出格式 `<block>yes</block>` 与 `<block>no</block>`；不得把 `temperature=0`、`stop_sequences` 或 exact suffix 作为硬条件。
- Stage 2 命中必须基于强特征：Claude Code 客户端、`/v1/messages`、非流、`max_tokens` 在 `4096..8192`、最后一条消息为 `user`、请求文本包含完整 `<transcript>...</transcript>`，并包含 XML classifier 输出格式 `<block>yes</block>` 与 `<block>no</block>`。Stage 2 suffix 文本与 `stop_sequences` 可作为人工核对线索，不作为硬条件。
- classifier 检测不得只依赖 `model`、`8192` 或请求体大小；这些只能作为日志字段或辅助保护。
- 默认 `passthrough` 或任何未命中的非流请求只要继续转发上游，就必须完整走现有 2.1.172 `/v1/messages` body/header profile：`cc_version`、`cch`、UA、`anthropic-beta`、Stainless 头等均按最终 body/header 重新生成，不能因为 `stream=false` 跳过。
- 本地 mock / error 的 classifier 请求不转发上游，因此不生成上游 `cc_version` / `cch` / Stainless 头；只返回 Claude Code 可解析的本地 message 或 error。
- 命中后日志必须区分 `auto_mode_classifier_stage1` / `auto_mode_classifier_stage2`，记录 `action`、`mode`、`account_id`、`model`、`max_tokens`、`body_bytes`、`text_bytes`、`message_count`、`retry_count`，不打印原始 prompt。
- Settings 页要能分别配置 Stage 1 / Stage 2 模式，并提示 `mock_allow` 返回 `<block>no</block>`。
- Settings 页同一全局设置区域提供流式稳定性配置：
  - `stream_keepalive_enabled`：默认关闭。
  - `stream_keepalive_interval_secs`：默认 `45`，允许 `5..240`。
  - `stream_upstream_idle_timeout_secs`：默认 `120`，允许 `30..1800`。
- 流式 keep-alive 开启后只作用于转发上游的流式 `/v1/messages` 响应；上游首个 chunk 到达前不得注入任何字节，避免影响首字时间。
- 流式 keep-alive 只插入 SSE comment：`: cc2api-keepalive\n\n`，不得伪造 Anthropic `data` 事件或 `{"type":"ping"}` 业务事件。
- Settings 保存后热刷新，无需重启容器。
- 历史数据库实例迁移后新增设置项有默认值。
- 旧版通用“非流辅助请求”配置与代码必须移除：`intercept_warmup_non_stream_aux_enabled`、`intercept_warmup_non_stream_aux_mode` 不再读写、展示或由 API 返回；迁移时清理历史 settings 行。

## Acceptance Criteria

- [ ] 默认配置下 Stage 1 / Stage 2 classifier 请求继续转发上游。
- [ ] Stage 1 设置为 `mock_allow` 后，强命中特征请求本地返回 `<block>no</block>`，不进入上游转发。
- [ ] Stage 2 设置为 `mock_allow` 后，强命中特征请求本地返回 `<block>no</block>`，不进入上游转发。
- [ ] Stage 1 / Stage 2 设置为 `mock_block` 后，返回可被 Claude Code 解析的 `<block>yes</block><reason>...</reason>` message。
- [ ] Stage 1 / Stage 2 设置为 `error` 后，返回标准 error object。
- [ ] 非 classifier 的 `max_tokens=8192` 或 `64000` 非流请求不被本轮规则拦截。
- [ ] 日志不泄露 Authorization、Cookie、token、password、secret 等敏感字段或完整 prompt。
- [ ] Rust 单测覆盖 Stage 1/Stage 2 检测、避免误拦 `8192/64000`、mock allow/block/error 响应。
- [ ] Rust 单测覆盖旧 `intercept_warmup_non_stream_aux_*` settings 行迁移清理。
- [ ] Rust 单测覆盖流式 keep-alive：首包前不注入、开启后静默间隔注入 SSE comment、关闭时不注入。
- [ ] 前端构建通过，Settings 页可保存新模式。

## Definition of Done

- `cargo fmt --check`
- `cargo test`
- `npm run build` in `/root/project/cc2api/web`
- `git diff --check`
- 部署前通过 `trellis-check-all`。

## Out of Scope

- 本轮不实现 `64000` non-streaming fallback 拦截。
- 本轮不实现 classifier cache replay。
- 本轮不实现通用 prompt 内容分类器。
- 不默认开启新拦截策略。
