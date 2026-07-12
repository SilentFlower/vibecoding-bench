# 上游 session 池一致性修复设计

## 设计目标

在不改变账号配置、sticky、RPM、队列和本地 stateful cache 隔离语义的前提下，保证：

1. 同一次 Claude Code 主请求的 body、`X-Claude-Code-Session-Id` 和自动 message telemetry 使用同一个 upstream session。
2. 账号容量缩小后，池在下一次 resolve/status 时原子收敛到新容量。
3. 同一真实 session 在映射目标仍活跃时保持稳定，不因其他成员变化重新取模。
4. 客户端 `event_logging` 只读复用主请求实际保存的映射。

## 数据模型

### MemoryStore

每个账号维护一个 `UpstreamSessionPoolState`：

```text
members: real upstream member -> last_seen_ms
mappings: real downstream session -> { upstream_session_id, last_seen_ms }
```

整个账号状态继续由同一个 mutex 保护，成员清理、容量裁剪、映射校验和更新在一次临界区内完成。

### Redis

继续保留现有成员 ZSET，并新增两个账号级 key：

```text
upstream_session_pool:{account_id}
  ZSET member=upstream_session_id score=member_last_seen_ms

upstream_session_pool_mapping:{account_id}
  HASH field=real_session_id value=upstream_session_id

upstream_session_pool_mapping_seen:{account_id}
  ZSET member=real_session_id score=mapping_last_seen_ms
```

三个 key 由同一个 Lua 脚本处理。映射记录使用与账号池相同的 TTL 窗口；主请求更新映射时间，遥测只读查询不更新时间。

## 原子解析算法

输入继续包括账号、真实 session、容量、TTL、刷新策略和 `allow_insert`。

1. 删除成员 ZSET 中超过 TTL 的成员。
2. 删除映射时间 ZSET 中超过 TTL 的真实 session，并同步删除映射 HASH 字段。
3. 如果成员数超过当前容量，按 `last_seen` 升序、session id 稳定顺序淘汰最旧成员，直到 `count <= pool_size`。
4. 读取真实 session 的已保存映射；只有目标仍存在于成员 ZSET 时才有效，否则删除该条陈旧映射并视为未命中。
5. 如果真实 session 自身是活跃成员，以自身为 upstream session；主请求刷新成员和映射时间，遥测查询不写状态。
6. 如果存在有效映射，继续复用目标：
   - `mapped_request` 主请求刷新目标成员 `last_seen`。
   - `owner_only` 借用请求不刷新目标成员。
   - 主请求刷新映射记录时间；遥测查询不刷新。
7. 如果是只读遥测且没有有效映射，返回 `None`，不再按当前成员集合临时取模。
8. 如果是主请求且池未满，接纳真实 session 为成员并保存 self mapping。
9. 如果是主请求且池已满，沿用稳定 hash 选择一个成员，并保存显式映射。后续成员集合变化不影响该映射，除非目标过期或被淘汰。
10. Redis 三个 key 设置有限过期时间；功能禁用期间不主动操作，重新启用后的第一次 resolve/status 按当前 TTL 和容量收敛。

## 容量收敛

- MemoryStore 对成员按 `(last_seen_ms, session_id)` 排序并删除超额项。
- Redis 使用 `ZRANGE 0 <excess-1>` 获取最旧成员；同分值时 Redis 按 member 字典序稳定排序。
- 不在裁剪时全量扫描映射 HASH。所有映射读取都必须校验目标仍在成员集合中，因此被淘汰目标立即逻辑失效；陈旧物理记录在该真实 session 下次访问或映射 TTL 清理时删除。
- `get_upstream_session_pool_status` 增加 `pool_size` 参数，使管理端读取也能执行容量收敛。

## Gateway 与 Header

Gateway 仍按以下顺序执行：

```text
真实 session 账号选择/sticky/RPM/队列
  -> resolve upstream session
  -> body rewrite
  -> 解析 rewritten body
  -> header rewrite
  -> 自动 message telemetry context
  -> 上游转发
```

Claude Code `/v1/messages` 只有在 `UpstreamSessionPoolResolve` 表明 `real_session_id != upstream_session_id` 时，才用 upstream session 覆盖 `X-Claude-Code-Session-Id`。这样客户端传入的真实 header 不会绕过实际发生的池映射，同时保留抓包中 warmup probe 可能出现 header/body 不一致的官方特殊行为。admitted、owner-hit 和失败开放路径没有改变 body session，不额外覆盖 header。

## 抓包依据

- 样本范围：`data/flows/*/*/*/http_capture.jsonl` 中 235 条 `/v1/messages?beta=true` 请求。
- 222 条正常请求全部满足 `X-Claude-Code-Session-Id == metadata.user_id.session_id`。
- 13 条 `max_tokens=1`、单条 5 字符 user message 的 warmup probe 中，12 条一致、1 条不一致。
- 异常样本是 Claude Code `2.1.173` Haiku warmup probe；Gateway 的 warmup 拦截发生在账号 admission 和 session 池解析之前。
- 结论：主请求的协议基线是 header/body 一致，但不能把一致性规则无条件扩展到所有 warmup/辅助请求。

## 遥测

- 自动 message request/result telemetry 保持从 rewritten body 构造 `MessageTelemetryContext`，无需改变事件模型。
- 客户端 `event_logging` 收集明确 session 字段后调用 `allow_insert=false`：
  - self member 或已保存有效映射命中时改写为对应 upstream session。
  - 映射缺失、目标过期、目标被容量裁剪或 cache 异常时失败开放。
  - 不创建成员、不临时取模、不刷新成员和映射 TTL。
- startup/GrowthBook telemetry 没有主请求对应关系，继续使用 telemetry run profile。

## 兼容与迁移

- 不修改数据库 schema、账号 API 或前端字段。
- 旧 Redis 只有成员 ZSET 时无需迁移。升级后的首次主请求会为真实 session 建立显式映射；首次只读遥测在无映射时失败开放。
- MemoryStore 重启后状态本来就会丢失，行为与现状一致。
- 回滚代码后新增 Redis mapping key 无副作用，并会按 TTL 自动过期。

## 风险控制

- Redis Lua 必须避免输出或记录完整 session。
- 映射数量与最近 TTL 窗口内发起主请求的真实 session 数一致，不新增长期持久化；不增加账号配置项。
- 不在热路径扫描所有映射，容量裁剪只与最大池容量 `20` 成正比。
- Redis 脚本异常继续由 Gateway 失败开放，body/header/自动遥测统一使用真实 session。
