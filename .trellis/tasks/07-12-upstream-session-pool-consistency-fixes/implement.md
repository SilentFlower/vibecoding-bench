# 上游 session 池一致性修复实施计划

## 1. 扩展池状态与接口

- 在 `src/store/cache.rs` 增加内部映射状态所需类型，并让 status 查询接收当前 `pool_size`。
- 保持 `resolve_upstream_session_pool(..., allow_insert)` 对外语义，明确只读 lookup 不创建、不刷新、不临时取模。
- 更新 `AccountService` 和所有 CacheStore 实现/测试调用点。

## 2. 修复 MemoryStore

- 将账号池从单一成员 Map 调整为成员与显式映射组合状态。
- 实现 TTL 清理、LRU 容量裁剪、映射目标有效性校验和主请求映射保存。
- 增加单测：
  - 容量 `5 -> 2` 后保留最近成员。
  - 映射目标未过期时，其他成员增删不改变映射。
  - 目标过期或被裁剪后，主请求重新映射，遥测只读返回空。
  - `mapped_request` / `owner_only` 刷新语义不回归。
  - 遥测 lookup 不创建、不刷新映射或成员。

## 3. 修复 Redis 原子脚本

- 为成员池增加 mapping HASH 和 mapping last-seen ZSET。
- 在单个 Lua 脚本内完成成员/映射 TTL 清理、LRU 容量裁剪、目标校验、resolve 和主请求映射写入。
- status Lua 接收容量并执行相同成员 TTL 清理与 LRU 裁剪。
- 三个 key 使用一致的有限 key TTL；陈旧映射允许逻辑失效后懒清理。
- 人工核对脚本并发语义：并发入池不超容量、缩容后不返回已淘汰目标、只读遥测不写状态。

## 4. 修复 Header 与遥测链路

- 仅当池解析结果满足 `real_session_id != upstream_session_id` 时，用 upstream session 覆盖最终 `X-Claude-Code-Session-Id`；不无条件规范化所有 Claude Code `/v1/messages` header。
- 增加 CC 客户端回归测试：输入 header 为真实 session、rewritten body 为 upstream session，最终 header/body 必须一致。
- 增加无实际 session 改写时不覆盖 header 的回归测试，保护 warmup/辅助请求的现有协议行为。
- 保留自动 message telemetry 从 rewritten body 取 session 的现有顺序，并增加关联断言。
- 更新 `event_logging` 测试，验证只使用显式已保存映射，成员集合变化时不重新取模。

## 5. 规格同步

- 更新 `.trellis/spec/cc2api/backend/service-architecture.md`：记录显式映射、LRU 缩容、header 覆盖和遥测只读 lookup 契约。
- 不修改账号配置、数据库、管理 API 和前端交互。

## 6. 验证

```bash
cd cc2api
cargo fmt --check
cargo test upstream_session
cargo test event_logging_session_fields
cargo test message_context_extracts_safe_counts_and_session_id
cargo test
cargo test cch

cd cc2api/web
npm run build
```

最后运行 `git diff --check`，检查日志和测试 fixture 不包含完整敏感 session 或请求体。

## 风险文件与回滚点

- `src/store/redis.rs`：Lua 原子脚本是最高风险点，失败时必须保持 Gateway 失败开放。
- `src/store/memory.rs`：必须与 Redis 语义逐项一致，作为可执行参考实现。
- `src/service/rewriter.rs`：只覆盖 session header，不改变其他 Claude Code header 画像。
- `src/service/gateway.rs`：保持账号 admission、body rewrite、header rewrite、telemetry context 的顺序不变；header 对齐必须以本次池解析是否实际改变 session 为条件。
- 回滚本次代码即可恢复旧算法；新增 Redis mapping key 会按 TTL 自动清理，无需数据回滚。
