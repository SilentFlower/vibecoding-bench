# cc2api Auto Mode classifier 实施计划

## Implementation Checklist

- [x] 新增 settings 默认值、DB migration、router GET/PUT 校验和热刷新。
- [x] 移除旧 `intercept_warmup_non_stream_aux_*` 配置读写、展示和历史 settings 行。
- [x] 扩展 `WarmupInterceptConfig` / `WarmupInterceptType`，增加 Stage 1 / Stage 2 classifier 模式。
- [x] 实现 Stage 1 / Stage 2 强特征检测。
- [x] 实现 `passthrough` / `mock_allow` / `mock_block` / `error` 四种模式。
- [x] 更新命中日志，区分 stage 和 action，不输出 prompt。
- [x] 更新 Settings.vue：预热请求拦截区域增加 Stage 1 / Stage 2 模式选择。
- [x] 添加 Rust 单测：Stage 1、Stage 2、非 classifier 8192/64000 不误拦、mock allow/block/error、旧 settings 清理。
- [x] 新增流式稳定性 settings、热刷新、Settings.vue 配置入口。
- [x] 实现首包后 SSE comment keep-alive，降低 `64000` non-stream fallback 触发概率，不影响首字时间。
- [x] 添加 Rust 单测：首包前不注入、开启后静默注入、关闭时不注入。
- [x] 执行验证命令。

## Validation

- `cargo fmt --check`
- `cargo test`
- `npm run build` in `/root/project/cc2api/web`
- `git diff --check`

## Review Gates

- 默认模式必须是 `passthrough`。
- mock allow 必须返回 `<block>no</block>`。
- 本轮不得新增 `64000` fallback 拦截或 cache replay。
- 流式 keep-alive 默认关闭，且必须只插入 SSE comment，不伪造 `data` 业务事件。
- 提交前运行 `trellis-check-all`。
