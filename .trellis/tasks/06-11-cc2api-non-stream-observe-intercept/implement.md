# cc2api 非流请求观测与拦截实施计划

## Implementation Checklist

- [ ] 先提交/处理 Settings 页 `step=1` 小修，避免与本任务核心 diff 混淆。
- [ ] 扩展 settings 默认值、DB migration、router GET/PUT 校验和热刷新。
- [ ] 扩展 `WarmupInterceptConfig` / `WarmupInterceptType`，新增非流辅助请求检测规则。
- [ ] 实现非流辅助请求 mock_text / error 两种响应模式。
- [ ] 为 `/v1/messages` 上游非 429 错误响应补充透传诊断日志；如确认响应头/body 不一致导致 newapi 显示 500，则重建错误响应时移除 `content-length`、`content-encoding`、`transfer-encoding`，保持原 status 和 body。
- [ ] 在 `forward_to_upstream` 中为开启日志的非流 `/v1/messages` 缓冲响应、记录响应摘要后重建响应。
- [ ] 更新 Settings.vue：预热请求拦截卡片新增非流辅助请求开关和响应模式。
- [ ] 添加/更新 Rust 单测：检测规则、响应模式、响应日志脱敏和截断、非 429 错误响应头清理/透传。
- [ ] 添加/更新前端类型和保存逻辑。
- [ ] 执行验证命令。

## Validation

- `cargo fmt --check`
- `cargo test`
- `npm run build` in `/root/project/cc2api/web`
- `git diff --check`
- 手动验证 Settings 保存和远程日志行为。

## Review Gates

- 默认拦截响应模式已确认：HTTP 200 固定 assistant 文本。
- 提交前运行 `trellis-check-all`。
- 部署前确认新拦截默认关闭，不会误伤现有流量。
