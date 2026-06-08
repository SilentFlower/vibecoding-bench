# cc2api cache_control TTL 改写设置实施计划

## Implementation Checklist

- [x] 增加 `cache_control_ttl_rewrite` 默认值常量和数据库默认插入项。
- [x] 在管理设置读取/更新接口中补齐默认值、校验枚举值。
- [x] 在 `GatewayService` 增加 TTL 改写配置缓存和 reload 方法。
- [x] 启动时加载 TTL 改写配置,设置更新后热刷新。
- [x] 在 `Rewriter` 增加 TTL 改写枚举/参数和只改已有 ephemeral cache_control 的 helper。
- [x] 将 TTL 改写接入 `/v1/messages` body 改写流程,并保证在 CCH attestation 计算前执行。
- [x] 更新 prime poller 或其他 `rewrite_body` 调用点,保持默认行为为 `off`。
- [x] 在设置页增加三选一控件,保存时提交新设置。
- [x] 增加/更新后端单元测试。
- [x] 运行格式化和测试,记录无法运行的环境原因。

## Validation

- `cargo test service::rewriter::tests` 通过。
- `cargo test` 通过。
- `cargo fmt --check` 已能运行,但失败于仓库既有 rustfmt 漂移;为避免夹带无关格式化,未执行全仓 `cargo fmt`。
- `git diff --check` 通过。
- `npm run build` 通过。

## Review Gates

- 实施前确认 PRD 中默认值与“不新增缓存断点”约束无异议。
- 代码完成后对照 sub2api 参考范围检查路径覆盖,避免引入新增断点逻辑。
- 提交前只提交 cc2api 代码和本任务相关 Trellis 文档,不夹带无关归档/日志变更。
