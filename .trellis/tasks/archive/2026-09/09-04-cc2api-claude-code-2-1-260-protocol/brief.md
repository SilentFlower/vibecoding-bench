# Brief — 适配 cc2api Claude Code 2.1.260 协议

## Goal

- 基于已完成的真实抓包证据，为 cc2api 新增独立的 Claude Code 2.1.260 默认画像，
  修复已确认的 2.1.257 Fable 5 历史漂移，并保留其余旧版本回滚能力。

## Scope

- 新增 2.1.260 identity、request、billing、endpoint 和 telemetry 画像，默认 profile
  与允许范围切换为 `2.1.260` / `2.1.89-2.1.260`。
- 按 Opus 5、Sonnet 5、Fable 5.1、Haiku 精确模型和请求类型实现 beta、thinking、
  fallback、body order、bootstrap、`cc_version` 与 CCH 契约。
- 修复 2.1.257 Fable 5 的 `fallbacks="default"`、fallback beta、CCH fallback 保留和
  bootstrap `marigold`，保持其余 2.1.257 与更旧画像兼容。
- 更新 rewriter、gateway、telemetry、OAuth、session hello、DB/settings、管理设置页、
  README 和对应回归测试。

## Non-Goals

- 不拉取或提交原始抓包、会话正文和生产凭据。
- 不发布生产镜像或迁移线上数据库；这些工作由后续部署任务负责。
- 不改变抓包未涉及的配额、代理、OAuth 所有权、默认模型或账号能力策略。

## Key Decisions

- 2.1.260 使用独立版本画像，不能通过修改 2.1.257 全局常量间接实现。
- wire profile、CCH fallback 与 bootstrap cwk 按精确模型 ID 选择，family helper 只用于
  已确认共享的配额或展示逻辑。
- `cc_version` 算法、CCH seed、Stainless、Node、Bun、endpoint/header/body 顺序和
  telemetry shape 保持抓包确认的不变值。
- DB/settings 只迁移仍等于 2.1.257 历史默认组合的值；管理员自定义 allowed range、
  system-role、1M allowlist、模型策略和账号能力必须保留。

## Key Context

- 权威证据位于归档抓包任务的 `research.md` 和
  `fixtures/claude-code-2.1.260-profile.json`，117 条 billing 样本的 `cc_version` 与
  CCH 已全量命中。
- 主要实现入口为 `version_profile.rs`、`rewriter.rs`、`gateway.rs`、`telemetry.rs`、
  `oauth.rs`、`session_hello_probe.rs`、`db.rs`、`settings_store.rs`、router、
  `Settings.vue` 和 README。

## Risks / Deferred

- 没有 2.1.260 Fable 5 和 Fable 5.1 `[1m]` 样本，不能外推 per-turn、display、
  fallback 或 1M 行为；相关路径保留兼容行为并明确延期。
- Sonnet 只有两条完成主请求，当前可建立精确画像，但异常重试和长会话变体仍需保持
  保守分类。
- 追加式默认列表迁移在代码回滚时不一定自动删除，只允许加入抓包明确且向后兼容的项。

## Acceptance

- 默认 identity、allowed range、canonical env、UA、build time 和 telemetry 一致切换到
  2.1.260，Stainless、Node 与 Bun 保持已确认值。
- 抓包覆盖的四类模型和请求类型与脱敏 fixture 一致，`cc_version`、CCH、beta、thinking、
  fallback 和 bootstrap 均有回归断言。
- 2.1.257 Fable 5 历史修正通过，其余 2.1.257 与更旧回滚画像保持兼容。
- 旧默认组合条件迁移正确，自定义设置和账号能力不被覆盖。
- `cargo fmt --check`、定向测试、`cargo test cch`、`cargo test`、Web `npm run build` 和
  Check-All 全部通过。

## Next Step

- Check-All 已通过；下一步进入 `trellis-update-spec`，确认本轮精确模型边界和迁移回归
  经验是否需要同步到项目规范。
