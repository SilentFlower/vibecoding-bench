# Brief — 支持删除账号

## Goal

- 让 WebUI 账号页的“删除”操作从用户视角真正移除账号；有关联历史时保留任务/批次/运行记录引用，但删除后的账号不再参与新任务、继续对话、额度查询或后台 OAuth access token 刷新。

## Scope

- 为 `accounts` 增加 `deleted_at REAL` 并在 `init_db()` 中幂等补列。
- 修改账号删除：无历史引用时物理删除；有关联 `tasks`、`runs`、`task_batches` 时软删除并隐藏。
- 修改 `/api/accounts` 默认列表，只返回未软删除账号，使账号页和所有账号下拉自动隐藏删除账号。
- 修改同名添加/登录：遇到同名软删账号时恢复原行、重新启用并清空 `deleted_at`。
- 收口所有可使用账号入口：额度查询、创建任务、创建批次、抓包 run、运行旧任务、继续对话、批次后台执行、后台 OAuth 刷新都必须只接受 `enabled=1 AND deleted_at IS NULL` 的账号。
- 修改前端删除账号成功后的提示逻辑，不再展示“账号仍有关联任务或运行记录，已改为停用。”。

## Non-Goals

- 不级联删除任务、批次、运行记录或磁盘 workspace/flows。
- 不删除 `data/profiles/<account>` 目录，也不调用外部 OAuth revoke。
- 不强停删除时已经在运行的 run；如需删除账号立即停止所有运行，后续单独处理。

## Key Context

- 当前 `delete_account()` 在有关联历史时只执行 `enabled=0` 并返回 `disabled: true`，前端据此弹出旧提示。
- `tasks.account_id`、`task_batches.account_id`、`runs.account_id` 都保存账号 ID；SQLite 默认不强制外键，但历史语义仍依赖账号引用。
- OAuth 后台刷新器当前按 `SELECT * FROM accounts WHERE enabled=1 ORDER BY id` 选账号；必须增加软删除过滤。
- 额度查询会启动临时 worker 调 OAuth usage API，并可能刷新后回写 `.credentials.json`；删除账号必须被后端拒绝。
- 运行结束的 `persist_worker_profile()` 只回写配置，不回写 OAuth 凭据；本任务不改变已经运行中的 run 收尾行为。
- 实现需遵守单文件 `orchestrator/main.py`、裸 `sqlite3`、写入 `_db_lock`、前端零构建和 `escapeHTML` 约定。

## Acceptance

- 删除一个有关联任务或运行记录的账号后，API 返回成功，账号页刷新后不显示该账号，且不弹出“已改为停用”。
- 删除后的账号不会出现在创建任务、批量任务、抓包 run 等账号选择下拉中。
- 删除后的账号不会被后台 access token 更新逻辑选中，也不会触发 profile token 写入。
- 删除后的账号调用额度查询、创建任务、创建批次、抓包 run、运行旧任务或继续对话时，后端返回明确错误，不启动 worker/sidecar。
- 已有任务、批次、运行列表不会因为账号被删除而崩溃；账号名展示可使用 `acc#<id>` fallback。
- 删除无历史引用账号时，账号行被物理删除。
- 重新登录/添加曾删除的同名账号时，恢复原软删账号行并重新启用，不因 `accounts.name UNIQUE` 报重复。
- 后端通过 `python3 -m py_compile orchestrator/main.py`；前端账号删除和下拉过滤路径完成手动验证。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `python3 ./.trellis/scripts/task.py start .trellis/tasks/07-08-support-account-deletion`，再进入 `trellis-route(implement)`。
