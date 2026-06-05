# cc2api 全局 Claude Code 版本与 UA 访问策略

## Implementation Checklist

- [x] 在 `src/store/settings_store.rs` 增加两个默认配置常量。
- [x] 在 `src/store/db.rs` 迁移默认 settings 中插入默认值。
- [x] 新增或扩展后端策略解析函数：
  - [x] 解析逗号/换行分隔列表。
  - [x] 支持 `*` UA pattern 匹配。
  - [x] 支持精确版本、通配版本、闭区间版本匹配。
- [x] 在 `GatewayService` 中增加内存缓存字段和 reload 方法。
- [x] 服务启动时加载访问策略配置。
- [x] `/admin/settings` 更新相关 key 后刷新网关访问策略。
- [x] 在请求入口、账号选择前执行策略校验。
- [x] 设置页新增 Claude Code 版本范围和允许 UA 输入项。
- [x] 更新 README 或相关说明，记录配置格式和默认兼容行为。
- [x] 增加/更新测试。

## Validation

- `cargo test --offline`
- `cargo check --offline`
- `cd web && npm run build`
- `git diff --check`

已执行：

- `docker run --rm ... rust:1.86-bookworm cargo check --offline`：通过。
- `docker run --rm ... rust:1.86-bookworm cargo test --offline`：通过，93 个 lib 单测、集成测试均通过。
- `docker run --rm ... rust:1.86-bookworm cargo test --offline access_policy`：通过，覆盖默认版本范围、`AI-Hub-Monitor*`、`python-httpx*`、UA 通配、版本通配和反向区间。
- `cd web && npm run build`：通过。
- `git diff --check`：通过。

未执行：

- `cargo fmt --check`：容器内 `rust:1.86-bookworm` 和 `rust:slim-bookworm` 均缺少 `cargo-fmt` 组件。

## Review Gates

- 默认配置必须按 `2.1.89-2.1.156` 限制 Claude Code / CLI，并允许 `AI-Hub-Monitor*`、`python-httpx*`。
- 拒绝逻辑必须在请求上游之前完成。
- UA 匹配不使用正则，避免复杂配置和性能风险。
- 错误日志和响应不得包含 token、请求体正文或上游敏感响应。

## Check All Result

- 三件套实现：通过。PRD / design / implement 中的配置项、默认值、通配规则、热刷新、入口拒绝、设置页和 README 均已落地。
- 假设验证：通过。前端提交 key 与后端 settings key 一致；后端更新后刷新网关缓存；网关在读取 body、账号选择和上游请求前拒绝。
- 跨层完整+规范：通过。新增策略模块复用同一套校验逻辑；默认值集中在 `service::access_policy` 并由 DB migration、settings API、网关和前端引用/对齐。
- Spec 更新：未写入 `.trellis/spec/`，原因是当前 spec 属于 `vibecoding-bench`，本任务业务代码位于独立的 `/root/project/cc2api` 仓库，避免把 cc2api 业务契约写入错误项目规范。
