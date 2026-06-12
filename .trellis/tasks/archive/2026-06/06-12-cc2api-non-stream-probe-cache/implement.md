# cc2api 非流单消息探针缓存实施计划

## Implementation Checklist

- [x] 在 cc2api 设置存储中新增 `non_stream_probe_cache_enabled` 默认常量，默认 `false`。
- [x] 在 DB 默认 settings 迁移中插入该设置。
- [x] 在 Settings API 中补默认值、校验 `true` / `false`，并在更新时刷新网关内存配置。
- [x] 在 `GatewayService` 增加 `NonStreamProbeCacheConfig` 与进程内缓存字段。
- [x] 实现 `reload_non_stream_probe_cache_config()`。
- [x] 实现非流单消息探针识别与 `probe_type` 分类。
- [x] 实现基于最终请求形态的缓存 key hash。
- [x] 在上游转发前插入缓存命中路径，命中时记录 `non_stream_probe_cache_hit` 并返回缓存响应。
- [x] 在上游成功返回后插入缓存创建路径，记录 `non_stream_probe_cache_create`。
- [x] 在 Settings 页面增加“非流单消息探针缓存”开关，保存后写入新 setting。
- [x] 补充单元测试：匹配条件、拒绝条件、开关关闭、命中、过期、日志字段。

## Validation

- `cargo fmt --check`
- `cargo test`
- 前端可用时运行 `npm run build` 或项目现有前端检查命令。

## Validation Results

- [x] `cargo fmt --check` 通过。
- [x] `cargo test` 通过；check-all 过程中第一次全量运行曾遇到既有账号调度时序测试 `test_sticky_rpm_saturation_rejects_instead_of_switching` 间歇失败，单独复跑通过，第二次全量复跑通过。
- [x] `cargo test service::gateway::tests::non_stream_probe -- --nocapture` 通过，覆盖新增缓存边界。
- [x] `cargo test --test account_store_timestamp_test test_create_account_with_oauth_timestamps -- --nocapture` 单独复跑通过。
- [x] `npm run build` 在 `web/` 通过。

## Check-all Notes

- [x] 修复探针识别边界：`messages[0].content` 为多个 text block 时不再按第一个 block 命中缓存，符合“唯一消息文本命中”约束。
- [x] 修复 Settings 页面布局与文案：429 请求观测区使用 4 列展示四个控件，开关文案为“非流单消息探针缓存”。

## Review Gates

- 实现前确认 PRD/design/implement 与用户需求一致。
- 实现后先运行定向测试，再运行全量 Rust 测试。

## Rollback

- 关闭 `non_stream_probe_cache_enabled` 即可恢复现有请求上游行为。
- 若需要代码级回滚，删除新增设置、缓存字段、命中/创建逻辑和前端开关。
