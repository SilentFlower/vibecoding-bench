# cc2api system role guard

## Implementation Checklist

- [x] 阅读相关 Trellis spec 和 cc2api 本地约定。
- [x] settings 默认值增加 `allow_system_role_models=claude-opus-4-8`。
- [x] `SettingsStore` 增加读取单个配置值的 helper。
- [x] `/admin/settings` 更新校验 `allow_system_role_models` 是逗号分隔模型 ID 列表，允许空字符串。
- [x] `GatewayService` 注入 `SettingsStore`。
- [x] `GatewayService` 缓存允许模型列表,避免请求路径每次查询 settings。
- [x] 启动时加载缓存,`/admin/settings` 更新白名单后刷新缓存。
- [x] 网关在请求体解析后、账号选择/遥测/队列/rewrite 前增加 `/v1/messages` system-role guard。
- [x] guard 使用请求体顶层 `model` 精确匹配允许列表。
- [x] 400 响应返回 `error`、`model`、`allowed_system_role_models`。
- [x] 增加后端测试，覆盖未命中拦截、命中放行、传统请求不拦截、错误响应包含允许列表。
- [x] 前端设置页增加全局模型列表读取、保存、输入和预设按钮。
- [x] README 补充开关说明。
- [x] 运行可用格式化和测试。

## Validation

- `cargo fmt --check`
- `cargo test --offline`
- `npm --prefix web run build`

## Validation Notes

- `npm --prefix web run build` 已通过。
- `git diff --check` 已通过。
- 当前环境没有可用 `cargo`，`cargo fmt --check` / `cargo test --offline` 运行失败：`cargo: command not found`。
- 补充优化已复核：请求路径已改为读取内存白名单缓存，不再每次查询 settings；启动时加载 settings，`/admin/settings` 更新白名单后刷新缓存。

## Review Gates

- 启动实现前确认 PRD/design/implement。
- 提交前确认本地 400 不会请求上游，也不会触发账号选择后的副作用，且错误响应返回当前允许模型列表。

## Rollback Points

- 后端 guard 改动集中在 `gateway.rs` 和 settings helper，若误拦截可单独回滚该段逻辑或把允许列表改为空/目标模型。
- settings 新增 key 兼容旧代码，发布回滚无需迁移删除。
