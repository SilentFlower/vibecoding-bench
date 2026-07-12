# Brief — 账号创建时选择时区

## Goal

- 让 `vibecoding-bench` 在账号创建 / 重新登录时可从下拉框选择账号时区，并让 OAuth 登录容器和任务 worker 使用该账号时区；未选择时保留现有按账号名派生时区。

## Scope

- 修改 `orchestrator/main.py`：新增 `accounts.timezone` nullable 列、时区允许列表校验、账号创建 / 恢复 / 重登写入、账号列表返回有效时区、登录 worker 与任务 worker 的 `TZ` 覆盖逻辑。
- 修改 `webui/index.html`：账号配置表单新增时区下拉框。
- 修改 `webui/app.js`：新建默认自动模式、重登回显显式时区、start/commit payload 携带 timezone、账号列表展示有效时区和来源。
- 允许列表只使用现有 `_TZ_POOL` 10 个时区，不加入 `Asia/Shanghai`。

## Non-Goals

- 不修改 `cc2api`。
- 不新增按国家 / 代理 IP 自动选择时区。
- 不改变 `LANG` / `LC_ALL`、hostname、MAC、machine-id、mem 的派生规则。
- 不改变历史 run 已记录的环境。

## Key Context

- 当前 `accounts` 表没有时区字段：`orchestrator/main.py:594`。
- 当前时区由 `derive_fingerprint(account_name)` 从 `_TZ_POOL` 派生：`orchestrator/main.py:1279`。
- 任务 worker 当前使用 `TZ=fp["tz"]`：`orchestrator/main.py:1442`。
- 登录 worker 当前使用 `TZ=fp["tz"]`：`orchestrator/main.py:2343`。
- 账号表单当前只有账号名和代理配置：`webui/index.html:368`。
- 登录 start/commit 复用 step 1 body：`webui/app.js:323`、`webui/app.js:448`。
- 风险点：`LoginStartIn` 同时用于 start 和 commit；同名重登的 `INSERT` 失败后 `UPDATE` 路径、软删除恢复路径都必须同步 timezone。

## Acceptance

- 新账号选择 `Europe/Berlin` 后，登录 worker 和后续任务 worker 的 `TZ` 都为 `Europe/Berlin`。
- 自动模式或旧客户端未提交 timezone 时，登录 worker 和任务 worker 仍使用现有按账号名派生的时区。
- 旧 DB / 旧账号无迁移操作即可继续运行，未设置显式时区时派生结果不变。
- 重新登录已有账号时下拉框回显当前显式配置，提交后同名账号 timezone 按表单更新。
- 非允许列表时区返回 400，不启动登录容器，不写 DB。
- WebUI 账号列表展示有效时区和 `auto` / `manual` 来源。
- 下拉选项不包含 `Asia/Shanghai`。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `task.py start .trellis/tasks/07-12-account-timezone-selection`，然后进入 Phase 2.1 `trellis-route(implement)`。
