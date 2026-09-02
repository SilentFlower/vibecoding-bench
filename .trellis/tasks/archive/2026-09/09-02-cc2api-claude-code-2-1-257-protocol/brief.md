# Brief — 适配 cc2api Claude Code 2.1.257 协议

## Goal

- 基于真实抓包新增 Claude Code 2.1.257 默认画像，并分别适配 Opus、Fable 5、
  Fable 5.1 与 Haiku 请求子画像，确保 hash、模型限制、设置迁移和流式超时诊断符合
  官方 wire 行为，同时保留 2.1.220 及更早画像的回滚能力。

## Scope

- 在 `src/service/version_profile.rs` 新增 2.1.257 identity、allowed range、模型/请求
  子画像、CCH 策略、Bun UA 和 bootstrap 参数，并切换默认画像。
- 在 `src/service/rewriter.rs` 按版本、请求类型和精确模型 ID 选择 beta、fallback、
  thinking、max tokens、body order 与 CCH 输入。
- 分别支持 Fable 5 与 Fable 5.1；5.1 使用 `fallbacks="default"`、64000 max tokens、
  adaptive thinking display updates 和独立 beta。
- 将 Haiku 2.1.257 区分为 probe、结构化 title、主请求和 1024 非流式辅助请求；
  title 通过 `output_config.format` JSON schema 结构识别，并保留旧字符串兼容。
- 将 Fable 5.1 加入 system-role 白名单和共享 Fable 周配额的候选过滤、sticky fallback、
  模型级 429 换号。
- 条件迁移默认 profile/range、账号 canonical env、system-role 和 bootstrap 默认设置，
  保留管理员自定义值。
- 区分零 chunk 首字节超时和首 chunk 后 idle timeout，在脱敏日志中记录 upstream
  request ID、等待时间和 chunk 数。
- 同步设置页、README、session hello、telemetry 和 TokenTester 的画像消费者。

## Non-Goals

- 不自动开放 Fable `[1m]`，不修改或迁移生产账号 `allow_1m_models`。
- 不主动给 Fable 5.1 注入 `context-1m-2025-08-07`；显式 token 继续按账号白名单过滤。
- 不自动把 Fable 5.1 加入 disabled-thinking 或 assistant-prefill 兼容列表。
- 不保证 Anthropic Fable 5.1 始终返回首个 SSE chunk，不伪造 SSE、不无限延长 timeout。
- 不处理尚未确认经过 `ANTHROPIC_BASE_URL` 的 code sessions、notification preferences、
  ultrareview 等新端点。
- 不提交完整抓包、prompt、响应正文、Authorization、Cookie、账号或代理凭据。

## Key Decisions

- Fable 5 与 Fable 5.1 是独立 wire profile；只有明确的配额 family 语义共享。
- CCH 改为画像驱动的字节级归一化：2.1.257 仍使用 seed
  `0x4D659218E32A3268`，Fable 5.1 必须保留 `fallbacks="default"` 参与 hash。
- Fable fallback 使用明确的 JSON shape 表达，不再用单个 fallback model 字符串推断。
- 原生 Claude Code 请求只补缺失字段；API mimicry 才按画像合成默认字段和字段顺序。
- system-role 使用一次性追加式迁移，精确去重后加入 `claude-fable-5-1`，保留
  `claude-sonnet-5` 等自定义模型。
- run `86926719c1ee` 显示 `[1m]` 入口解析为 Fable 5.1 后实际 message 请求没有 1M
  beta，因此本轮不把 bootstrap 的 `[1m]` 展示解释为强制注入协议。
- 首字节超时只改善诊断：首个真实 chunk 前不注入 keepalive，120 秒保护不扩大到
  Claude Code 的约 184 秒 watchdog。

## Key Context

- 主要模块：`version_profile.rs`、`rewriter.rs`、`gateway.rs`、`account.rs`、
  `settings_store.rs`、`db.rs`、`router.rs`、`session_hello_probe.rs` 和 Web 设置页。
- Fable 5.1 抓包：`9333aa5d1fe3`、`724f47b5673c`、`86926719c1ee`；Haiku 抓包：
  `ea6d8e9bb665`。脱敏结论位于父任务 `research/`。
- 当前 rewriter 只精确识别 `claude-fable-5`，5.1 会使用错误 beta、fallback、max tokens
  和 CCH 路径。
- 当前线上 profile/range 为 2.1.220；system-role 自定义列表不含 5.1，账号
  `allow_1m_models` 不含 `fable`。
- Fable 5.1 成功请求和 no-response 请求使用相同 beta/CCH；错误根因是上游零首字节，
  不是 CCH、beta 或 HTTP 状态。

## Risks / Deferred

- CCH 输入是最终序列化字节，任何字段顺序或归一化偏差都会造成全量签名不命中。
- 默认设置迁移若覆盖自定义 range 或模型列表，会造成生产策略回归。
- 误扩展 disabled-thinking 会破坏 Fable 5.1 的真实 adaptive display 请求。
- 误注入 1M beta 会偏离抓包并可能改变计费或上下文行为。
- Anthropic 上游零首字节问题无法由本任务消除；只保证超时保护和诊断信息正确。
- 新端点的 base URL 路由证据不足，延后到独立任务。

## Acceptance

- 默认 profile、UA、Stainless、Bun、allowed range、telemetry env 和 canonical env 均为
  2.1.257，2.1.220 回滚画像测试不回归。
- Opus、Fable 5、Fable 5.1、Haiku 脱敏 fixture 的 `cc_version` 与 CCH 全量复算命中。
- Fable 5/5.1 各自获得正确 beta、fallback、thinking、max tokens 和 body order；5.1
  system-role 请求不再本地 400，并进入共享周配额和模型级 429 换号。
- Haiku 四类请求选择对应 beta，新 title 不依赖 prompt 原文即可识别，旧 title 兼容。
- 无 1M beta 的 Fable 5.1 请求不会被注入；显式 1M beta 只在账号 allowlist 命中时透传。
- 零 chunk 超时日志包含 request ID、等待时间、`chunk_count=0` 和明确阶段；首 chunk 后
  idle timeout 与 keepalive 语义不回归。
- profile/range 只迁移历史默认组合；system-role 追加 5.1 并保留自定义值；
  assistant-prefill、disabled-thinking、`allow_1m_models` 不被迁移。
- `cargo fmt --check`、定向测试、`cargo test cch`、全量 `cargo test` 和 Web 构建通过。

## Next Step

- 调用 `task.py start` 激活本子任务，然后通过 `trellis-route(target=implement)` 选择
  实现执行方式，并首先修改版本画像与脱敏 hash fixture 测试。
