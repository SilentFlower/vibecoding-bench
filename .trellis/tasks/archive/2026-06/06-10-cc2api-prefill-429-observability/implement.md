# implement.md

## Implementation Checklist

- [x] 读取 Trellis 后端/前端/共享规范和 cc2api 现有模式。
- [x] 在 settings_store/db/router/main/gateway 增加 assistant prefill 拦截配置。
- [x] 在 gateway 增加 prefill 检测、模型匹配和本地 400 响应。
- [x] 在 settings_store/db/router/main/gateway 增加 429 请求观测配置。
- [x] 在 gateway 429 分支增加脱敏、截断后的请求抓取日志。
- [x] 在 Settings.vue 增加新配置 UI、加载、保存和输入校验。
- [x] 增加 Rust 单测覆盖检测、匹配、脱敏、截断。
- [x] 运行格式化、测试、前端构建和 diff 检查。

## Validation

- `cargo fmt`
- `cargo test assistant_prefill --lib`
- `cargo test rate_limit_request --lib`
- `cargo test --lib`
- `npm --prefix web run build`
- `git diff --check`

## Review Gates

- 开发前确认 assistant prefill 默认模型列表策略。
- 检查日志脱敏不能泄露 token/Authorization/Cookie。
- 检查默认关闭,升级后不改变行为。
