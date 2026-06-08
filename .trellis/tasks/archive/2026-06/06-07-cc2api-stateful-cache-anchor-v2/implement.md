# implement.md

## Implementation Checklist

- [x] 对比当前 `rewriter.rs` 与旧 commit `3f5cce8` 的 anchored 实现，提取可复用的 fingerprint / state store 代码，避免原样恢复旧逻辑。
- [x] 新增 `MessageCacheControlRewrite::Stateful`，解析 settings 值，保留旧 `anchored -> auto` 兼容或按设计决定是否迁移到 stateful。
- [x] 将 `Rewriter` 从无状态 struct 改为持有 `Mutex<StatefulCacheStore>` 或等价并发安全状态。
- [x] 实现 `RequestProfile` 计算：block_count、message_count、tool_result_count、assistant_tool_use_count、tail role/type、last user text hash。
- [x] 实现请求分类：`NormalLinear`、`TransientSpike`、`ParallelSibling`、`Unknown`。
- [x] 实现 fingerprint：剥离 `cache_control`，包含 role/type/block hash/邻近 hash。
- [x] 实现 stateful 选点：旧 anchor 复用优先，剩余 slot 按当前 auto tail/bridge 补齐。
- [x] 实现 promotion 规则：正常请求更新主线锚点，异常请求只临时选点不污染状态。
- [x] 实现并发覆盖保护：generation 或 profile compare，防止 stale/transient 请求覆盖 normal anchors。
- [x] 增加诊断日志字段：request_class、block_count、normal_block_count、reused_count、promotion reason、selected。
- [x] 更新 README 和设置说明。
- [x] 更新前端 Settings.vue 和 API 类型，新增 `stateful` 选项。
- [x] 增加 Rust 单元测试覆盖正常复用、`76 -> 567 -> 78` 防污染、并发覆盖保护、重复 block、TTL、CCH、非 Claude Code 忽略。
- [x] 运行验证命令。

## Validation

- [x] `cargo test message_cache_control --lib`
- [x] `cargo test`
- [x] `npm run build --prefix web`
- [x] `git diff --check`

## Review Gates

- 实现前按 Trellis 路由选择 implement 模式。
- 提交前按 Trellis 路由选择 check 模式。
- 不提交 `/root/project/vibecoding-bench` 中与本任务无关的旧 archive / journal 脏文件。

## Rollback Points

- 配置切回 `auto` / `rolling` / `off`。
- 若 stateful 状态异常，重启进程清空内存状态。
