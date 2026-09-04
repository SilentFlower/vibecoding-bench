# 实施计划

## 1. 消费抓包证据

- [x] 读取 2.1.260 `research.md`、差异矩阵和最小 fixture。
- [x] 建立“证据 -> 画像字段/分类器 -> 测试”映射，标记保持不变和延期项。

## 2. 新增 2.1.260 画像

- [x] 在 `version_profile.rs` 新增独立画像并切换默认 profile/range。
- [x] 更新 rewriter/gateway/telemetry/OAuth/session hello 等消费者。
- [x] 按精确模型和请求类型实现抓包证明的 beta、body、fallback、thinking、bootstrap、
      `cc_version` 和 CCH 差异。
- [x] 修复 2.1.257 Fable 5 的 `fallbacks="default"`、fallback beta、CCH fallback 保留和
      bootstrap `marigold`，保持其余 2.1.257 画像与更旧回滚行为不变。
- [x] 对 2.1.260 Fable 5 和 Fable 5.1 `[1m]` 保持证据不足边界，不外推未观察行为。

## 3. 迁移与前端

- [x] 增加 2.1.257 旧默认组合到 2.1.260 的条件迁移和账号 canonical env 迁移。
- [x] 保留自定义 allowed range、system-role、1M 和账号能力。
- [x] 更新 Settings 默认值、回滚按钮和 README。

## 4. 验证

- [x] 运行 `cargo fmt --check`。
- [x] 运行画像、rewriter、CCH、gateway、DB 和 telemetry 定向测试。
- [x] 使用脱敏 fixture 断言 2.1.260 四类模型与 2.1.257 Fable 5 历史修正。
- [x] 运行 `cargo test cch` 和 `cargo test`。
- [x] 运行 `cd web && npm run build`。
- [x] 执行 Check-All，确认抓包矩阵正反向覆盖完整。
