# 账号级上游 session 池实施计划

## 实施步骤

1. 扩展账号模型与校验
   - 在 `Account` 增加 upstream session pool 字段和刷新策略枚举/解析。
   - 在 create/update handler 校验容量 `0` 或 `1-20`、TTL `5-1440`、策略值。
   - 保持默认关闭，推荐值为 size `3`、TTL `60`、policy `mapped_request`。

2. 扩展数据库与 store
   - SQLite / PostgreSQL schema 增加四个账号字段。
   - migration 使用幂等 `ALTER TABLE ... ADD COLUMN`，老账号默认关闭。
   - 更新 `row_to_account`、`create`、`update`、`ACCOUNT_COLS`。
   - 补 SQLite migration/store 单测。

3. 扩展 cache 抽象
   - 在 `CacheStore` 增加 upstream session pool 解析与状态读取方法。
   - Redis 使用 Lua 保证清理、计数、插入、映射和刷新原子执行。
   - MemoryStore 用 mutex 存储账号池成员并模拟同样语义。
   - 单测覆盖容量、TTL、稳定哈希和两种刷新策略。

4. 接入 Gateway / Rewriter
   - `GatewayService` 在账号确定、admission 通过、body rewrite 前解析 upstream session override。
   - `rewrite_body_with_stateful_completion` 传入可选 override。
   - `rewrite_metadata_user_id` 改写 JSON 和 legacy `session_id`。
   - header 重写继续从 rewritten body 提取 session，保持 body/header 对齐。
   - 自动遥测 context 必须在 upstream session 改写后的 body 上构造，确保 message request/result event 使用 upstream session。
   - event_logging / telemetry payload 中的明确 session 字段应复用已有池成员映射，且不得创建新池成员。
   - 本地 stateful cache key 使用真实 session，避免跨真实 session 污染。

5. 前端账号配置
   - 更新 `web/src/api.ts` Account 类型。
   - 在 `Accounts.vue` 账号表单加入开关、容量、TTL、刷新策略。
   - 账号列表展示当前池活跃数/容量，文案突出默认关闭与作用范围。

6. 任务收敛
   - 根据最终实现更新 PRD/设计中如有偏差的字段名或约束。
   - 用 `trellis-task-brief` 生成 brief，给用户确认后再 `task.py start`。

## 验证命令

```bash
cd cc2api
cargo fmt --check
cargo test
```

如果修改前端：

```bash
cd cc2api/web
npm run build
```

补充检查：

```bash
git diff --check
```

## 风险点

- Redis 原子性：并发新 session 同时入池不能超过容量。
- stateful cache：不能因为 upstream session 复用而把多个真实 session 的本地 cache 状态合并。
- telemetry：自动遥测和客户端 event_logging 不能绕过池暴露真实 session；但 telemetry 映射失败时应失败开放，不阻断请求。
- 协议顺序：session body 改写必须发生在 CCH / `cc_version` 重新计算前。
- 默认值：老账号升级后必须默认关闭，避免无意改变协议行为。
- 日志隐私：不要输出完整 session id、完整 `metadata.user_id` 或请求体。

## 回滚点

- 将账号 `upstream_session_pool_enabled=false` 或 `upstream_session_pool_size=0` 即可恢复旧行为。
- 如 Redis 解析异常，代码应失败开放并使用真实 session，避免请求中断。
