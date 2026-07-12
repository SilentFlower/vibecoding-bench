# 账号创建时选择时区

## Goal

让 `vibecoding-bench` 在账号创建 / 重新登录时支持用户从下拉框选择账号时区，并让后续 OAuth 登录容器和任务 worker 使用该账号时区。未显式选择时保留现有按账号名派生时区的行为，避免破坏已有账号和批量运行。

## Background

- 当前账号表 `accounts` 只存代理、启用状态和软删除字段，没有时区字段：`orchestrator/main.py:594`。
- 当前 `derive_fingerprint(account_name)` 按账号名 `sha256` 从 `_TZ_POOL` 中派生 `tz`，并继续派生 `lang`、`hostname`、`mac`、`machine_id`、`mem`：`orchestrator/main.py:1279`。
- 普通 / 批量任务 worker 通过环境变量 `TZ=fp["tz"]` 使用派生时区：`orchestrator/main.py:1442`。
- OAuth 登录 worker 也通过环境变量 `TZ=fp["tz"]` 使用派生时区：`orchestrator/main.py:2343`。
- WebUI 添加账号弹窗目前只有账号名和代理配置，没有时区控件：`webui/index.html:368`。
- WebUI 新建 / 重登账号时会把 step 1 表单内容传给 `/api/accounts/login/start`，commit 时复用同一份 body：`webui/app.js:323`、`webui/app.js:448`。
- 后端 `AccountIn` 和 `LoginStartIn` 目前不接收时区字段：`orchestrator/main.py:3554`、`orchestrator/main.py:3705`。
- 用户已确认下拉框不加入 `Asia/Shanghai`。

## Requirements

- R1：账号创建和 OAuth 登录流程必须支持一个账号级时区字段，字段值为允许列表内的 IANA 时区名。
- R2：允许列表固定为现有 `_TZ_POOL` 的 10 个时区：`Asia/Tokyo`、`Asia/Singapore`、`Asia/Seoul`、`Australia/Sydney`、`Europe/London`、`Europe/Berlin`、`Europe/Paris`、`America/Los_Angeles`、`America/New_York`、`America/Chicago`；不得加入 `Asia/Shanghai`。
- R3：WebUI 添加账号弹窗必须提供时区下拉框；用户可选择显式时区，也可选择默认自动模式。
- R4：显式选择时区后，`accounts` 表必须持久化该值；账号列表 API 必须返回显式时区和当前有效时区，便于重登时回显和列表展示。
- R5：任务 worker 与 OAuth 登录 worker 必须优先使用账号显式时区；没有显式时区时继续使用 `derive_fingerprint(account_name)` 的派生时区。
- R6：已有账号升级后必须兼容；没有时区列或列为空时行为不能变化。
- R7：软删除恢复、同名重新登录覆盖账号配置时，时区配置必须按当前表单值更新。
- R8：时区校验必须拒绝任意字符串，避免把无效 `TZ` 写入容器环境。
- R9：账号列表应能看出当前账号使用的有效时区，并能区分自动模式与显式选择。

## Acceptance Criteria

- [ ] 新账号选择 `Europe/Berlin` 后，登录 worker 和后续任务 worker 的 `TZ` 都为 `Europe/Berlin`。
- [ ] 新账号选择自动模式或未提交时区字段时，登录 worker 和后续任务 worker 仍使用现有按账号名派生的时区。
- [ ] 已有账号在升级后不需要数据迁移操作即可继续运行，且未设置显式时区时派生结果不变。
- [ ] 重新登录已有账号时，时区下拉回显当前显式配置；提交后同名账号的时区配置按表单更新。
- [ ] API 对不在允许列表中的时区返回 400，不启动登录容器，也不写入 DB。
- [ ] WebUI 账号列表展示每个账号的有效时区，并标明自动或手动来源。
- [ ] 下拉选项不包含 `Asia/Shanghai`。
- [ ] 验证至少覆盖后端时区解析 / 默认回退，以及前端静态资源可加载。

## Out Of Scope

- 不修改 `cc2api` 的时区或账号画像。
- 不新增按国家 / 代理 IP 自动选择时区的能力。
- 不改变 `LANG` / `LC_ALL`、hostname、MAC、machine-id、mem 的派生规则。
- 不改变历史 run 的已记录环境。
