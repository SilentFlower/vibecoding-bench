# 支持删除账号 - 设计

## 目标

账号删除要从“有关联就停用并继续显示”改为“有关联则软删除并隐藏”。删除后的账号不再进入任何新任务、继续对话、额度查询或后台 OAuth access token 刷新路径；历史任务、批次和运行记录保留。

## 数据模型

- `accounts` 新增 `deleted_at REAL`。
- `_SCHEMA` 中补列，`init_db()` 中通过 `_ensure_column(conn, "accounts", "deleted_at", "REAL")` 兼容既有 SQLite。
- 账号可用条件统一为 `enabled=1 AND deleted_at IS NULL`。
- 无历史引用的账号仍物理删除；有 `tasks`、`runs`、`task_batches` 引用时执行 `UPDATE accounts SET enabled=0, deleted_at=? WHERE id=?`。

## API 行为

- `GET /api/accounts` 默认只返回 `deleted_at IS NULL` 的账号。这样账号页和所有依赖 `/api/accounts` 的下拉天然隐藏已删除账号。
- `DELETE /api/accounts/{aid}`：
  - 找不到账号或已软删除账号时返回 404。
  - 无引用时物理删除并返回 `deleted: true`。
  - 有引用时软删除并返回 `deleted: true, soft_deleted: true`；不再返回 `disabled: true` 触发前端旧提示。
- `POST /api/accounts/{aid}/quota` 只接受可用账号。额度查询会走 OAuth usage 探测，可能刷新 token，所以删除账号必须在这里被拒绝。
- `POST /api/tasks`、`POST /api/task-batches`、`POST /api/captures/run`、`POST /api/tasks/{tid}/run`、`POST /api/runs/{rid}/continue/start` 都只接受可用账号。
- 批次后台执行 `_execute_batch()` 重新读取账号时也只读取可用账号；如果批次账号已删除，后续不再投放新 run。

## 同名重新添加

- `create_account()` 和 `login_commit()` 遇到同名已软删除账号时，恢复原行：更新 `profile_path`、代理配置、`enabled=1`、`deleted_at=NULL`。
- 同名未删除账号保持现有行为：创建接口继续报 `account exists`，登录 commit 视为重授权并更新代理配置。
- `_infer_deleted_account_id()` 继续服务于历史误删恢复；软删除账号存在时不走该推断路径，直接恢复同名软删行。

## OAuth access token 刷新边界

- `OAuthRefreshScheduler._tick()` 查询账号时增加 `deleted_at IS NULL`。
- `Runner.refresh_account_oauth_token()` 增加防御：如果传入账号不是 `enabled=1 AND deleted_at IS NULL`，直接跳过，不启动 sidecar/worker，不写 `.credentials.json`。
- `query_account_quota()` 使用同一可用账号校验，避免删除账号通过 quota usage 探测刷新并回写 token。
- 已经运行中的 worker 不在本任务中强停；现有 `persist_worker_profile()` 只回写配置，不回写 OAuth 凭据，避免扩大删除账号对正在运行任务的影响。

## 前端行为

- `/api/accounts` 过滤后，账号页、任务下拉、批次下拉、抓包下拉都会自动隐藏软删除账号。
- 删除按钮成功后只刷新账号页；移除 `result.disabled` 的“已改为停用”提示。
- 历史 runs/tasks 仍使用现有 `acc#<id>` fallback。若账号已隐藏，列表不崩溃即可。

## 非目标

- 不级联删除任务、批次、运行记录或磁盘 workspace/flows。
- 不删除 `data/profiles/<account>` 目录，也不调用外部 OAuth revoke。删除后的账号只是退出系统可用集合和刷新集合。
- 不强停删除时已经在运行的 run；如需删除账号立即停止所有运行，应作为独立需求处理。

## 风险与回滚

- 风险：漏掉某个账号读取入口会让删除账号仍可被使用。缓解：统一检查 `SELECT * FROM accounts` 调用点，并在关键入口加可用账号过滤。
- 风险：软删除同名恢复处理不完整会被 `accounts.name UNIQUE` 卡住。缓解：创建和登录 commit 两条路径都显式处理同名软删行。
- 回滚：移除 `deleted_at` 过滤会恢复旧行为；新增列为 nullable，不影响旧数据读取。
