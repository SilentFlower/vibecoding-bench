# 技术设计

## 设计目标

用最小改动修复 scope 扩权错误，同时保留现有刷新触发窗口、sidecar 网络、RT 轮换锁和 cc2api managed OAuth 边界。失败可观测性使用账号表安全状态字段，不引入新的日志框架或敏感响应落盘。

## 影响边界

- `orchestrator/main.py`
  - 后台刷新 probe 的 scope 构造与响应写回。
  - `OAuthRefreshScheduler` 的单账号结果收口和状态持久化。
  - accounts schema 兼容列、账号列表安全字段。
- `images/worker/entrypoint.sh`
  - 401 强制刷新时的 scope 构造与响应写回。
- `orchestrator/test_main.py`
  - 调度行为、状态持久化、脱敏和 probe 请求回归测试。
- 必要时更新 OAuth/部署 spec，固化“只能沿用已有 scope，不能 refresh 扩权”的契约。

## Scope 构造契约

两条 Node 刷新逻辑采用同一规则：

1. 读取 `oauth.scopes`。
2. 仅保留非空字符串，去除首尾空白。
3. 按首次出现顺序去重。
4. 结果非空时写入 `requestBody.scope = scopes.join(' ')`。
5. 结果为空时不创建 `scope` 字段。

OAuth refresh 不能借刷新流程扩大授权范围；这也是避免旧账号因新增客户端权限而出现 `invalid_scope` 的核心不变量。

## 刷新结果写回

- `access_token` 必须存在，否则失败。
- `refresh_token` 有新值时替换，否则保留旧值。
- `expiresAt` 沿用现有 `expires_in` 计算。
- 响应存在有效 scope 时写回归一化数组；响应缺失 scope 时保留原数组。
- `subscriptionType`、`rateLimitTier` 保持现有兼容写回行为，不扩大本次改动。

## 后台状态模型

在 `accounts` 增加兼容列：

```text
oauth_refresh_last_attempt_at REAL
oauth_refresh_last_status     TEXT
oauth_refresh_last_error      TEXT
```

- 只有未绑定账号发生真实 refresh 尝试时更新。
- `success` 清空 error；`failed` 保存脱敏摘要。
- `_needs_refresh()` 判定为 false 时不更新，避免每分钟制造无意义写入。
- 绑定账号继续使用 cc2api 路径，不写本地 refresh 状态。
- 更新使用 `_db_lock`、事务和参数化 SQL；外部 Docker/OAuth IO 必须在 DB 锁外完成。

## 错误脱敏

复用最小安全摘要策略，不保存原始异常全文：

- 允许：`HTTP 400`、`invalid_scope`、`invalid_grant`、`429`、整数 `retry_after_sec`、固定本地错误类别。
- 移除或替换：Bearer/token 字样后的值、Authorization、Cookie、代理密码、超过固定长度的响应详情。
- 状态更新失败不能覆盖原 refresh 异常，也不能中断后续账号扫描。

## 调度容错

`OAuthRefreshScheduler._tick()` 对每个账号独立捕获异常并更新失败状态，然后继续循环。数据库首轮读取失败仍按既有行为结束本次 tick；单账号重读或状态落库失败不得永久终止调度线程。

## 兼容性

- `init_db()` 使用现有 `_ensure_column` 机制补列，旧 SQLite 无需删除或手工迁移。
- API 只增加字段，不删除或重命名现有字段。
- worker 与 orchestrator 都必须更新镜像；只部署其中一个会留下另一条错误刷新路径。
- 回滚到旧镜像时新增列保留但不影响旧代码。

## 部署与回滚

- 本地检查通过后提交并触发三镜像构建；本次实际受影响的是 orchestrator 与 worker。
- 远程按规范 `pull` 后 `up -d --force-recreate orchestrator`，并确保 `WORKER_IMAGE` tag 与新版一致。
- 部署前不修改生产 credentials；验证优先检查镜像、schema/API、安全状态和后续自然刷新结果。
- 回滚使用上一个已知 tag force-recreate；数据库新增列无需回滚。
