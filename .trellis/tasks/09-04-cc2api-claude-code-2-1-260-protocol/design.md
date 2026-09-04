# 技术设计

## 证据门禁

实现前读取抓包任务的 `research.md` 和最小 fixture，将每项结论映射到画像字段或明确的
request classifier。证据不足项保留 2.1.257 行为或延期，不以 npm 包版本号推导。

抓包回查已确认 2.1.257 Fable 5 存在历史漂移：fallback 应为字符串 `"default"`，
fallback beta 应为 `server-side-fallback-2026-07-01`，CCH 应保留 fallback，bootstrap
应使用 `marigold`。这些修正与 2.1.260 新画像一起实施，其余 2.1.257 行为保持回滚兼容。

## 画像结构

- `ClaudeCodeProfile` 保存 2.1.260 identity、billing、request、endpoint 和 telemetry
  字段。
- 版本级共享仅用于抓包证明稳定的属性；模型和请求类型差异继续由子画像表达。
- CCH 策略表达 top-level `model`、`max_tokens`、`fallbacks` 等字节级处理，不能先做
  JSON 反序列化再重排。
- 精确模型 ID 决定 wire profile；family helper 仅用于已确认共享的配额或展示。
- 没有 2.1.260 Fable 5 和 Fable 5.1 `[1m]` 样本时，不从 Fable 5.1 普通入口外推
  per-turn、display、fallback 或 1M 行为。

## 消费者

- `rewriter.rs`：beta、字段补齐、body order、`cc_version`、CCH。
- `gateway.rs`：请求分类、bootstrap、流式诊断和 system-role 边界。
- `telemetry.rs` / `oauth.rs` / `session_hello_probe.rs`：版本身份与 endpoint UA。
- `db.rs` / `settings_store.rs` / router：条件迁移和热刷新默认值。
- `Settings.vue` / README：默认画像、回滚选项和可操作说明。

## 迁移

- 仅当 profile 和 allowed range 同时等于 2.1.257 历史默认组合时迁移到 2.1.260。
- 账号 canonical env 按当前默认画像迁移版本身份字段，不改变能力开关。
- 其他设置只有抓包证明默认行为变化且当前值仍等于旧默认时才迁移。
- 管理员自定义列表使用精确追加/去重，不允许整体覆盖。

## 测试

- 画像单元测试覆盖新默认、2.1.257 Fable 5 历史修正、2.1.257 其余回滚和更旧画像。
- rewriter 使用脱敏 fixture 覆盖各模型/请求类型的 body、beta、`cc_version` 和 CCH。
- DB 测试覆盖旧默认组合升级、自定义 range 保留和账号能力不变。
- gateway/telemetry/endpoint 测试覆盖抓包确认的新增差异。

## 回滚

管理员可切回 2.1.257 profile/range；发布层同时保留旧镜像和 DB 备份。追加式列表迁移
不一定在代码回滚时自动删除，因此只允许加入抓包明确需要且向后兼容的精确模型项。
