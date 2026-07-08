# 支持删除账号

## Goal

让 WebUI 账号页的“删除”操作真正从用户视角移除账号，不再因为存在关联任务、批次或运行记录而只显示“已改为停用”，同时避免破坏历史任务/运行记录对 `account_id` 的引用。

## Confirmed Facts

- 当前后端 `DELETE /api/accounts/{aid}` 会统计 `tasks`、`runs`、`task_batches` 对账号的引用；只要引用数量大于 0，就执行 `UPDATE accounts SET enabled=0` 并返回 `disabled: true`。证据：`orchestrator/main.py:825`、`orchestrator/main.py:3537`。
- 前端账号页在收到 `result.disabled` 时弹出“账号仍有关联任务或运行记录，已改为停用。”证据：`webui/app.js:159`。
- `tasks.account_id`、`task_batches.account_id`、`runs.account_id` 都保存账号 ID；任务、批次、运行记录已有 `deleted_at` 软删除字段，但 `accounts` 当前没有 `deleted_at`。证据：`orchestrator/main.py:594`、`orchestrator/main.py:619`、`orchestrator/main.py:635`、`orchestrator/main.py:671`。
- 项目约定 SQLite 默认不校验外键，但仍用外键表达数据关系；因此直接硬删账号虽然技术上可能留下孤儿引用，但会破坏历史数据语义。证据：`.trellis/spec/vibecoding-bench/backend/database-guidelines.md`。
- 当前 `list_accounts()` 返回全部账号，未过滤 `enabled=0`；因此“停用”账号仍会出现在账号列表，以及依赖 `/api/accounts` 的任务/抓包账号下拉中。证据：`orchestrator/main.py:3518`、`webui/app.js:594`、`webui/app.js:633`、`webui/app.js:1081`。
- 后台 OAuth 刷新器 `OAuthRefreshScheduler._tick()` 当前按 `SELECT * FROM accounts WHERE enabled=1 ORDER BY id` 选择账号，未考虑软删除字段。证据：`orchestrator/main.py:2491`、`orchestrator/main.py:2544`。
- 账号额度查询 `POST /api/accounts/{aid}/quota` 会按账号启动临时 worker 读取 OAuth usage API，并可能刷新后回写 `.credentials.json`；删除账号后该接口也必须拒绝该账号。证据：`orchestrator/main.py:1634`、`orchestrator/main.py:1707`、`orchestrator/main.py:3559`。
- 单任务创建、批次创建、旧任务再次运行、继续对话和批次后台执行都有按 `account_id` 读取账号的路径，其中部分当前只校验账号存在，未校验启用或软删除。证据：`orchestrator/main.py:4007`、`orchestrator/main.py:4073`、`orchestrator/main.py:2797`、`orchestrator/main.py:4377`、`orchestrator/main.py:4674`。

## Requirements

- R1：账号删除成功后，账号页不再显示该账号，前端不再展示“已改为停用”的提示。
- R2：删除有关联任务、批次或运行记录的账号时，不直接留下不可解释的孤儿历史；历史任务/运行记录仍能按 `account_id` 回溯到账号名，或以稳定 fallback 展示。
- R3：被删除账号不能再用于创建新任务、批次、抓包 run、旧任务再次运行、继续对话、额度查询或后台 access token 更新。
- R4：删除无关联历史的账号时，应继续支持物理删除，避免保留无价值数据。
- R5：重新登录/添加同名账号时，应有明确行为，不能因隐藏账号导致唯一约束错误或重复账号歧义。
- R6：实现必须遵守现有单文件 FastAPI、裸 sqlite3、`_db_lock` 写入保护、前端零构建和 `escapeHTML` 约定。

## Acceptance Criteria

- [ ] 删除一个有关联任务或运行记录的账号后，`DELETE /api/accounts/{aid}` 返回成功，账号页刷新后不显示该账号，且不弹出“已改为停用”。
- [ ] 删除后的账号不会出现在创建任务、批量任务、抓包 run 等账号选择下拉中。
- [ ] 删除后的账号不会被后台 access token 更新逻辑选中，也不会触发 profile token 写入。
- [ ] 删除后的账号调用额度查询、创建任务、创建批次、抓包 run、运行旧任务或继续对话时，后端返回明确错误，不启动 worker/sidecar。
- [ ] 已有任务、批次、运行列表不会因为账号被删除而崩溃；账号名展示要么仍可解析，要么使用 `acc#<id>` fallback。
- [ ] 删除一个没有任何历史引用的账号时，数据库中该账号行被物理删除。
- [ ] 重新登录/添加一个曾删除的同名账号时，系统恢复原软删账号行，重新启用并清空 `deleted_at`，不会因为 `accounts.name UNIQUE` 报重复账号。
- [ ] 相关后端变更通过可用的语法/接口级验证；前端变更通过账号删除和下拉过滤路径的手动验证。

## Technical Notes

- 给 `accounts` 增加 `deleted_at` 软删除列；有关联历史时软删除账号并从 `/api/accounts` 默认列表中过滤，保留历史引用；无引用时仍物理删除。
- 创建/登录同名账号时，如果存在同名软删账号，恢复该账号行并更新 profile/proxy/enabled/deleted_at，避免 `accounts.name UNIQUE` 阻塞重新添加。
- 所有读取账号的运行入口和后台 token 更新入口都必须检查账号可用条件：`enabled=1 AND deleted_at IS NULL`。

## Decisions

- 删除有关联账号时采用“账号软删除并隐藏，历史记录保留”策略。
- 删除后的账号必须排除在后台 access token 更新范围之外，避免继续刷新或写入这些账号的 token。

## Out of Scope

- 不级联删除任务、批次、运行记录或磁盘 workspace/flows。
- 不删除 `data/profiles/<account>` 目录，也不调用外部 OAuth revoke。删除后的账号只是退出系统可用集合和刷新集合。
- 不强停删除时已经在运行的 run；如需删除账号立即停止所有运行，应作为独立需求处理。
