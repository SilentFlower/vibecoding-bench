# cc2api 升级 Claude Code 2.1.169

## Implementation Checklist

- [x] 读取 cc2api 相关规范和现有测试，确认数据库与服务层约定。
- [x] 更新 `version_profile` 默认版本、基础版本和 build time。
- [x] 更新访问策略默认范围、settings UI 默认值和 README 文档。
- [x] 调整 CCH seed 选择逻辑，显式支持 `2.1.156` 与 `2.1.169` 同 seed。
- [x] 在启动迁移中升级 settings 旧默认值和已有账号 `canonical_env` 版本字段。
- [x] 修复 stateful usage SSE buffer 超限修剪的 UTF-8 边界 panic。
- [x] 更新或新增单元测试覆盖默认版本、允许范围、CCH seed 和迁移行为。
- [x] 新增中文多字节字符跨截断点的 stateful usage buffer 回归测试。
- [x] 运行 cc2api 相关测试与格式检查。

## Validation

- `rustfmt --edition 2024 --check src/service/access_policy.rs src/service/gateway.rs src/service/rewriter.rs src/service/telemetry.rs src/service/version_profile.rs src/store/db.rs`：通过。
- `cargo test`：通过。
- `cargo test stateful_cache_usage_buffer_trims_on_utf8_boundary`：通过，覆盖原始字节截断点落在中文 UTF-8 字符中间的 panic 场景。
- `npm run build`（`/root/project/cc2api/web`）：通过。
- `git diff --check`：通过。
- `cargo fmt -- --check`：未作为通过项；仓库既有多个无关文件不符合 rustfmt，本任务未保留这些无关格式化 diff。
- Check-all inline：三件套实现、假设验证、跨层完整性与规范检查均通过，未发现需要暂停修复的 P0/P1 问题。

## Review Gates

- 开始实现前确认任务进入 `in_progress`。
- 完成实现后按 Trellis check 流程做质量验证。
