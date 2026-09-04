# 适配 cc2api Claude Code 2.1.260 协议

## Goal

基于已完成的 Claude Code 2.1.260 真实抓包证据，为 cc2api 新增独立默认画像，适配
已观察模型与请求类型的 wire 行为、设置迁移和管理界面，并保留 2.1.257 完整回滚
能力。

## Requirements

- 本任务必须等待 `09-04-claude-code-2-1-260-capture-evidence` 形成可复算结论；没有
  抓包证据时不得实现或猜测新 CCH、beta、模型子画像和 endpoint 行为。
- `version_profile.rs` 新增 2.1.260 identity、request、billing、endpoint、telemetry
  等画像，并将默认 profile/range 切换为 2.1.260 / `2.1.89-2.1.260`。
- 2.1.257 必须继续作为独立回滚画像保留；除抓包已确认的 Fable 5 历史漂移外，不能
  修改旧画像常量来间接适配新版本。Fable 5 必须修正为 `fallbacks="default"`、
  `server-side-fallback-2026-07-01`、CCH 保留 fallback、bootstrap `marigold`。
- Opus、Sonnet、Fable 5.1、Haiku以及证据中出现的其他精确模型分别按抓包选择 beta、
  fallback、thinking、body order、bootstrap 和 CCH 策略。
- 没有 2.1.260 Fable 5 和 Fable 5.1 `[1m]` 证据时不得外推新画像；继续保留已确认的
  兼容行为和显式证据不足标记。
- `cc_version`、CCH seed 和字节级输入归一化必须有脱敏 fixture 全量命中测试；旧算法
  命中也必须由测试证明。
- 更新 `rewriter`、`gateway`、OAuth、telemetry、session hello 等画像消费者，避免
  新旧版本共用会破坏回滚的全局常量。
- DB/settings 只迁移仍为 2.1.257 历史默认组合的 profile/range/canonical env 和抓包
  已证明需要迁移的默认值；管理员自定义 allowed range、system-role、1M allowlist、
  模型策略和账号能力必须保留。
- 设置页加入 2.1.260 默认画像和 2.1.257 回滚选项，README 同步精确事实。
- 新增辅助请求或 endpoint 如不能安全纳入现有分类，拆为独立子任务或明确延期，不能
  使用宽泛模型前缀或正文字符串吞掉未知行为。

## Acceptance Criteria

- [ ] 默认 profile、allowed range、账号 canonical env、User-Agent、Stainless、Bun、
      build time 和 telemetry identity 一致为 2.1.260。
- [ ] 所有抓包覆盖的模型/请求类型，其 beta、body、fallback、thinking、bootstrap、
      `cc_version` 和 CCH 与证据一致，fixture 全量命中。
- [ ] 2.1.257 回滚画像的其余行为保持通过，并新增 Fable 5 fallback、beta、CCH 与
      bootstrap 历史修正回归测试。
- [ ] 旧默认 DB/settings 条件迁移到 2.1.260，自定义值和账号能力不被覆盖。
- [ ] `cargo fmt --check`、`cargo test`、`cargo test cch`、Web `npm run build` 和
      Check-All 通过。

## Out of Scope

- 不在本任务拉取或提交原始抓包。
- 不发布生产镜像或迁移线上数据库；由发布子任务负责。
- 不改变抓包未涉及的配额、代理、OAuth 所有权和模型产品策略。
