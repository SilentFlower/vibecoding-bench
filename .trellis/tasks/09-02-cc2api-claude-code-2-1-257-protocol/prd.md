# 适配 cc2api Claude Code 2.1.257 协议

## Goal

基于真实抓包新增 Claude Code 2.1.257 默认画像，并分别适配 Opus、Fable 5、
Fable 5.1 与 Haiku 请求子画像，确保 hash、模型限制、设置迁移和流式超时诊断符合
官方 wire 行为。

## Confirmed Evidence

- 默认身份：`2.1.257`、build time `2026-09-01T05:28:54Z`、Stainless `0.112.1`、
  Node `v26.3.0`、Bun `1.4.1`。
- `cc_version` 仍使用现有 SHA256 文本位置算法；Opus、Fable 5.1 与 Haiku 样本均命中。
- CCH seed 仍为 `0x4D659218E32A3268`。2.1.257 需要把 `model` 置空并删除
  `max_tokens`；Fable 5.1 的 `fallbacks: "default"` 必须保留参与 hash。
- Fable 5 与 Fable 5.1 是两个独立模型。5.1 使用 `max_tokens=64000`、
  `fallbacks="default"`、adaptive thinking display updates 和独立 beta 顺序。
- Fable 5.1 主请求含 `messages[].role=system`，并与 Fable 5 共用上游
  `seven_day_fable` 配额窗口。
- run `86926719c1ee` 由 `[1m]` 入口发起，但 Claude Code 解析为 Fable 5.1 后，实际
  message 请求不携带 `context-1m-2025-08-07`。该行为发生在直连官方链路中。
- 两份 Fable 5.1 多轮抓包都复现上游首字节卡死：收到 200 headers 或建立请求后，
  长时间没有 SSE body，约 184 秒由客户端超时并重试；相同画像下也存在正常成功请求。

## Requirements

- 新增 2.1.257 内置画像并设为默认，保留 2.1.220 及更早回滚画像的 identity、UA、
  beta、fallback、bootstrap 和 CCH 行为。
- 将默认 allowed range 更新到 `2.1.89-2.1.257`，只迁移仍处于历史默认组合的
  settings；管理员自定义 allowed range 不得覆盖。
- 让请求改写按“版本 + 请求类型 + 精确模型 ID”选择子画像，不再把全部非 Fable
  请求合并为一个 beta，也不把 Fable 5.1 当成旧 Fable 5。
- Fable 5.1 使用抓包对应 beta、`fallbacks="default"`、64000 max tokens、body
  order、thinking display updates 和 CCH 输入；Fable 5 保持旧画像。
- Fable 5.1 加入 system-role 白名单和 Fable family 配额判断，包括候选过滤、sticky
  fallback 和模型级 429 换号；迁移线上列表时追加新模型并保留已有自定义模型。
- Haiku 2.1.257 按 probe、结构化 title、主请求和 `max_tokens=1024` 非流式辅助请求
  选择 beta。title 优先通过 `output_config.format` JSON schema 结构识别，旧 prompt
  字符串只作为兼容兜底。
- 将 CCH 归一化改为画像驱动并允许模型级差异，避免继续按版本字符串硬编码一个统一的
  `fallbacks` 删除规则。
- 更新 bootstrap configured 模式的 2.1.257 默认选项、`sorrel` 和 cedar basin；
  passthrough 模式保持不改上游，回滚画像保留旧配置。
- session hello、telemetry、TokenTester 和设置页均使用所选画像的 identity，不通过
  修改共享常量破坏旧版本。
- 首字节超时日志必须区分“0 chunk 首字节超时”和“已经收到 chunk 后的 idle timeout”，
  记录脱敏 account、upstream request ID、等待时间和 chunk 数，不记录请求正文。
- 不在首个真实 upstream chunk 前注入 keepalive，不伪造 SSE，不无限延长 timeout。
- 不自动给 Fable 5.1 注入 `context-1m-2025-08-07`，不迁移账号
  `allow_1m_models`。即使客户端显式传入，仍按账号白名单执行现有过滤策略。
- 不自动把 Fable 5.1 加入 disabled-thinking 或 assistant-prefill 列表；当前抓包没有
  证明需要这些旧兼容规则。

## Acceptance Criteria

- [ ] 默认 profile、UA、Stainless、Bun、allowed range、telemetry env 和账号
      canonical env 均为 2.1.257，2.1.220 回滚画像测试不回归。
- [ ] 脱敏抓包样本覆盖 Opus、Fable 5、Fable 5.1、Haiku 四类请求；`cc_version` 与
      CCH 全量复算命中，Fable 5.1 保留 `fallbacks="default"` 参与 CCH。
- [ ] Fable 5 和 Fable 5.1 各自获得正确 beta、fallback、thinking、max tokens 和
      body order；5.1 system-role 请求不再本地 400。
- [ ] Fable 5.1 进入共享周配额过滤、sticky fallback 和模型级 429 换号，旧 Fable 5
      行为不回归。
- [ ] Haiku probe、结构化 title、主请求和非流式辅助请求选择对应 beta；新 title 不依赖
      prompt 原文也能识别，旧 title 仍兼容。
- [ ] `[1m]` 回归测试证明：无 1M beta 的 Fable 5.1 请求不会被注入；显式 1M beta
      只有账号 allowlist 命中时才透传，默认账号策略不改变。
- [ ] 0 chunk 超时日志包含 request ID、等待时间、chunk_count=0 和明确原因；收到首个
      chunk 后的 idle timeout 仍按原语义工作。
- [ ] settings 迁移只升级历史默认 profile/range；system-role 列表追加 5.1 并保留
      自定义值；assistant-prefill、disabled-thinking、allow_1m_models 不被迁移。
- [ ] `cargo fmt --check`、`cargo test`、`cargo test cch` 和 `cc2api/web` 构建通过。

## Out of Scope

- 不保证 Anthropic Fable 5.1 上游始终返回首个 SSE chunk。
- 不自动开放 Fable `[1m]`，不修改生产账号 allowlist。
- 不基于未验证路由处理 `/v1/code/sessions`、notification preferences 或 ultrareview
  等新端点；若确认它们经过 `ANTHROPIC_BASE_URL`，另行补充范围。
- 不提交完整抓包、prompt、响应正文、Authorization、Cookie、账号或代理凭据。
