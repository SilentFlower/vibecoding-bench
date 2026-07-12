# Brief — 修复上游 session 池一致性问题

## Goal

- 修复账号级上游 session 池的 header/body、容量、稳定映射和遥测一致性，确保同一次请求及关联遥测使用同一个实际 upstream session。

## Scope

- Claude Code `/v1/messages` 仅在 session 池实际把 body 改为不同 upstream session 时覆盖最终 `X-Claude-Code-Session-Id`。
- MemoryStore 和 Redis 增加带 TTL 的 `real_session_id -> upstream_session_id` 显式映射。
- 容量缩小时按 `last_seen` 从旧到新原子淘汰，时间相同时按 session id 稳定排序。
- 映射目标仍活跃时保持复用；目标过期或被淘汰后旧映射立即逻辑失效。
- 客户端 `event_logging` 只读复用已保存映射，不创建成员、不刷新 TTL、不按当前成员重新取模。
- 更新账号池 code-spec，并补齐 MemoryStore、header/body 和 telemetry 回归测试。

## Non-Goals

- 不新增或修改账号配置字段、默认值、数据库 schema、管理 API 和前端交互。
- 不改变自动 telemetry 启动事件和 GrowthBook run session。
- 不限制下游真实 session 并发，不改变 sticky、RPM、队列和本地 stateful cache 使用真实 session 的语义。

## Key Context

- Redis 使用成员 ZSET、mapping HASH、mapping last-seen ZSET，由单个 Lua 脚本原子处理 TTL 清理、LRU 收敛和 resolve。
- MemoryStore 用单个账号状态 mutex 实现同等语义，作为 Redis 行为的可执行参考。
- 容量裁剪不全量扫描映射；每次读取映射都校验目标仍在成员池，因此被淘汰目标立即逻辑失效，物理记录按访问或 TTL 清理。
- 自动 message telemetry 继续从 rewritten body 构造 context；启动类 telemetry 仍使用独立 run session。
- 抓包中 222 条正常请求全部 header/body 一致；13 条 warmup probe 有 1 条官方不一致样本，因此不能无条件覆盖所有 message header。
- Redis/cache 异常继续失败开放，body、header 和自动 message telemetry 统一退回真实 session。
- 最高风险文件是 `src/store/redis.rs`、`src/store/memory.rs`、`src/service/rewriter.rs` 和 `src/service/gateway.rs`。

## Acceptance

- Claude Code 主请求发生实际池映射后，最终 body、`X-Claude-Code-Session-Id` 和自动 message telemetry session 一致；未改写 body session 时不额外覆盖 header。
- 功能关闭或 cache 失败开放时，header/body 都保持真实 session。
- 容量从 `5` 调到 `2` 后，下一次 resolve/status 活跃成员不超过 `2`，并保留最近活跃成员。
- 其他成员增删时，只要映射目标仍活跃，同一真实 session 不切换 upstream session。
- 目标过期或被淘汰后，主请求可以重新映射；只读 telemetry 不复活目标、不创建成员。
- `event_logging` 使用最近一次有效主请求保存的映射，不重新取模。
- `mapped_request` / `owner_only`、sticky、RPM、队列和 stateful cache 语义不回归。
- `cargo fmt --check`、定向测试、`cargo test`、`cargo test cch`、Web build 和 `git diff --check` 全部通过。

## Next Step

- 用户确认本 brief 后运行 `task.py start`，随后进入 `trellis-route(implement)`，默认交给实现子代理执行。
