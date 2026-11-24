# 反重力账号节点迁移

## Scenario: AGY 已登记运行环境双向迁移

### 1. Scope / Trigger

- 已登记的 AGY 网关账号在本机和 SSH 节点之间变更执行归属。按网关账号 ID 关联原环境，CC 工程账号继续按自己的账号空间分配。

### 2. Signatures

- `GET /api/agy-accounts/nodes` 返回 `{items: [assignment]}`。`GET /api/agy-accounts/{account_id}/node` 返回一项并包含 `migration_ready`。浏览器沿原管理会话访问相同路径的 `/runtime` 前缀。
- `GET|POST /api/agy-accounts/{account_id}/node-migrations` 读取最近操作或后台登记。`POST` 使用 `{operation_id,node_id,revision,version}`，`operation_id` 为 32 位小写十六进制，`node_id` 和 `revision` 为正整数，`version` 为 `1.5.9`。读取单项和 `POST /{operation_id}/resume|cancel` 沿原操作执行。
- `AgyLocation` 固定 `{node_key,account_id,environment_id,assignment_revision,generation}`。Node 私有 `agy-*` 通过已核验的安装身份与执行 Agent，回执带 `protocol:1` 及该操作的原范围。
- `bench.agy-nodes.6` 登记 `agy_node_assignments` 和 `agy_node_migrations`。两表用 `platform_api_environments.gateway_account_id` 作账号外键。

### 3. Contracts

- 分配返回 `account_id,node_id,node_key,node_name,kind,enabled,revision,phase`。已有环境与首次登记环境从本机版本 1 开始。迁移目标使用已启用且同批准备的节点。目标的镜像角色、批次、AGY 制品、系统画像和容量均在关接单前核验。
- 网关用 `node-migration:<operation_id>` 持有原账号排他许可。请求和工具续轮沿原准入留在源节点，续轮取 AT 时核对同一个账号的凭据许可、有效请求槽及 `draining` 阶段。网关持有 OAuth 刷新权。采集和管理入口按实际环境与代次路由。
- 排空后核实源角色已经停止。归档和解包均校验文件摘要与范围。可迁移资料为工程及工作区、CPU 策略、脱敏记录与快照、当前选中的已核验内核候选。发送绑定、AT 工作副本、热进程与 CRIU 模板由目标按已保存的账号配置重新准备。
- 目标实际环境沿同一 `environment_id` 产生更高代次。归属事务比较原节点、分配版本、账号和源代次。目标激活证明通过后恢复 API 准入。排空中取消保留原进程，源已隔离时先核对目标撤销再恢复源，归属提交后沿原目标继续激活。
- 页面读当前归属。`execution_location` 由原尝试的实际传输冻结，历史位置沿原尝试读取。代理变更沿原配置许可静默当前角色。网关删除远程账号后，仅在完整列表和原账号 404 一致且原停止代次无角色时标记 `retired`，保留历史位置和资料。
- 平台换批读取 `agy_update_blockers`。远程仍有活跃归属或 AGY 迁移未收口时，更新与回退均在切换前中止。完成或取消原迁移并将远程账号迁回本机后可换批。已核对无实际角色的归档归属可保留历史。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 首次登记或旧本机环境补齐 | 本机分配版本 1 |
| 目标未准备、制品或容量不兼容 | 开始接口返回 409，原归属及接单状态保留 |
| 错平台、旧分配、旧代次、错归档摘要 | 拒绝使用回执，保留原有效归属 |
| 归属已提交且激活回包丢失 | `resume` 核对原目标，`cancel` 返回 409 |
| 账号已停止且网关仍保留账号 | 保留 `ready` 归属与节点关联 |
| 平台换批存在远程活跃归属或未结束迁移 | 宿主返回具体阻断原因，原组件保持运行 |

### 5. Scenarios and Examples

- 正常。本机当前分配版本为 1，提交 `{"operation_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","node_id":2,"revision":1,"version":"1.5.9"}`。核对节点 2 的实际代次后持久化版本 2，回迁时以 2 为原版本提交。
- 边界。节点列表暂不可读时，当前页面保留上次已知节点；历史请求继续显示原执行位置。收到过期版本的迁移操作时重新读取当前分配，再发起新的操作。

### 6. Tests Required

- `test_agy_node_migration` 覆盖跨账号空间、历史本机归属、目标预检、原绑定排空、并发版本竞争、归档范围、删除确认和各换批模式。
- 网关 `agy_migration_only_continues_the_original_admission` 覆盖原请求、错账号许可、无活动和通用维护门禁。浏览器用 `verify_cluster_ui.py` 与 `verify_execution_node_visibility.py` 核对迁移、取消以及当前和历史位置。
- 隔离的真实 AGY 发送器和 SSH Agent 覆盖迁出、迁回、并发热更新、工具回填、提交前撤销和提交后恢复。对照合成上游请求逐次核对单次投递；具备 CRIU 恢复权限的部署验证迁移后实际启动来源。

## Scenario: AGY 默认运行环境与后台补热

### 1. Scope / Trigger

- AGY 账号 OAuth 已就绪时默认登记运行环境。网关启动和周期巡检补齐历史登记，并在当前所属节点为符合准入的账号准备一个实际空闲进程。

### 2. Signatures

- `POST /internal/v3/agy-environments/{account_id}?prepare=false|true` 使用编排服务鉴权。缺省为 `false`。回执含 `environment_id,generation,state`。状态为 `registered`、`bound`、`unprepared` 或 `failed`。仅 `bound` 携带私有 `binding`。
- `POST /internal/agy/warm` 使用当前发送器绑定鉴权。请求固定为 `account_id,environment_id,generation,request_id,deadline_unix_ms,credential_snapshot,capture_enabled`。受管 SSH 节点通过同一归属的发送隧道转发。
- 热准备以 `prepared` 和 `job_finalized` 两条私有事件收口。前者在 `ready` 时携带实际 `native_pid`，业务占用时回报 `busy`。两条事件均绑定原请求和环境代次。
- `GET /admin/native-preparations` 返回按 `account_id` 归属的状态数组。缺少可信绑定时，`scope="account"` 携带受控账号原因。

### 3. Contracts

- 网关先提交账号与 OAuth 状态，再幂等登记 `platform_api_environments`。重复触发和首次业务共用网关账号唯一绑定。登记失败的账号由全平台启动扫描和 20 秒巡检补齐。
- AGY 状态变更、重授权、代理变更和删除的持久结果沿原 `notify_native_change(id, true)` 失效旧准备。协调器清除原退避，撤销在途准备并重读权威账号。确认账号已经删除后清除该账号的准备快照。
- 新环境在内部指纹保存 `agy_initial_preparation_pending=true`。后台在代次为零、有首启资格且节点容量有余量时启动。角色就绪或显式停止会收口首启资格。首次启动前的配置静默保留该资格。历史指纹缺此字段时沿原状态判定。
- 运行环境的后台准备沿实际节点及环境代次，遵守节点分配、账号和 OAuth 状态、工作控制及系统维护门禁。首次后台启动走 `allow_eviction=False`。
- 网关复用已生效的业务采集模式和同代 AT-only 快照。监督器复用实际热进程池和原握手。所有后台准备的模型调用数为零。正在运行或等待工具回填的业务优先使用物理工位。单名额用于一个实际热进程，可恢复的同代模板须完成恢复才计入空闲 PID。
- `GET /api/environments` 以发送器实测空闲进程为热就绪依据。等待容量及失败回执只投影到相同环境代次。发送器空闲关停由原监督器写实际停止回执，正常重启后从同一环境重新补热。
- `scope="account"` 的 `credentials_not_ready`、`agy_environment_unavailable` 和 `orchestrator_upgrade_required` 只补充同账号空闲卡片的 `agy_runtime.preparation_reason`。物理状态、PID 和代次以实际环境观测为准。
- 监督器登记取消时在同一条件锁下唤醒容量等待。预热在原截止内收到取消后以 `request_cancelled` 收口。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 首次登记完成且节点容量充足 | 后台申请绑定并建立热进程 |
| 节点容量已用满 | 保留卡片，返回 `unprepared / waiting_capacity`，后续巡检重试 |
| 账号、节点暂停或切换 | 后台准备等待原门禁开放 |
| 凭据待核对或登记绑定失败 | 网关返回受控账号级原因，同账号卡片展示该原因 |
| 显式停止或历史环境已停止 | 保持休眠，依原业务入口唤醒 |
| 降容后容量等待中收到取消 | 唤醒已登记的预热请求，沿原请求输出终态 |
| 错账号、错代次或已过截止 | 私有发送器拒绝本次准备 |
| 原监督器缺实际停止回执 | 环境进入对账流程，保留原业务收口保护 |

### 5. Scenarios and Examples

- 正常。保存一个 OAuth 就绪账号，调用登记入口取得同一个环境 ID。容量释放后用 `prepare=true` 获取当前绑定，应用同代快照开始零模型准备。
- 边界。并发额度为 1。原工具轮等待回填时热准备回报 `busy`，下次空闲巡检补位。
- 边界。`{"account_id":17,"scope":"account","state":"unprepared","reason":"credentials_not_ready"}` 给账号 17 的等待卡片补充原因。重授权完成后的即时检查刷新账号原因。
- 错误用法。拿上一次环境代次的准备回执标记当前环境为热就绪。重新读取当前绑定和实测空闲 PID 后更新卡片。

### 6. Tests Required

- 编排层用 `test_agy_capture_api`、`test_agy_environment` 和 `test_agy_node_migration` 验证账号唯一、容量等待、停止与当前代次投影。
- `agy_account_changes_recheck_prewarm_before_backoff_expires` 核对启停、重授权、换代理、账号删除和受控失败原因。`test_cancel_warm_wakes_the_capacity_waiter` 核对降容等待的取消和零模型提交。
- `test_agy_supervisor` 验证数字为 1 的物理额度、旧工具轮优先及凭据换代。隔离 `verify_agy_prewarm.py` 核对首笔热命中、实际进程退出、换代、发送器正常重启、网关启动扫描及模型调用总数。
- `verify_agy_environment_ui.py` 核对等待准备、容量原因、准备失败和真实热进程就绪文案。

## 账号删除与专属环境退役

### 1. 适用范围

账号管理删除反重力网关账号，或工程账号页删除已保存的 Claude 账号时，按实际绑定和节点清理专属环境。

### 2. 接口与登记

- `DELETE /admin/accounts/{id}` 在配置租约内调用 `POST /internal/v3/agy-environments/{id}/prepare-deletion`。网关提交后调用同前缀的 `/retirement`。后台重试使用原 `environment_id`。
- `DELETE /api/accounts/{aid}?environment_id={eid}` 接受账号页看到的不可变环境 ID。工程删除范围含账号、绑定、环境、节点、分配版本和运行代次。

### 3. 资源与历史

先记录范围，再由实际所有者移除 CLI、发送器和网络角色，清理运行凭据副本和进程检查点。个人 HOME 配置、项目和历史引用保留。工程环境的原行归档为 `state='retired'`，反重力保留平台映射并将节点分配标为 `retired`。单独解绑继续沿用凭据交接流程。

### 4. 校验与失败

- 节点断连或实际移除回执缺失时保留原范围，巡检重试。同名重建使用独立环境 ID。
- 已归档的工程环境从账号环境列表和登录草稿中移出。对旧环境发起停止、重建或对账返回 404。已在等待环境锁的维护操作取得锁后重新核对归档状态。
- 节点升级核对旧版已关闭草稿的保存及激活记录、已删除账号、所属节点、完整容器 ID、标签和实际停止状态。归属冲突时保留现场。

### 5. 示例

反重力删除中途节点断开，恢复连接后对原账号和代次继续清理。工程账号重新以同名保存后，旧页面重试删除原环境得到成功回执，新环境继续可用。用旧环境 ID 请求重建时，从当前账号页重新读取有效环境。

### 6. 回归依据

`test_deleted_binding`、`test_cluster_owner_node`、`test_agy_node_migration` 和 `test_cluster_synchronization` 核对数据保留、实际移除、重复删除和历史升级。用 `verify_agy_accounts_ui.py` 核对反重力卡片和详情标题依次采用原生 `userTier` 名称、额度快照 `tier`、旧 `plan`。详情分别标明订阅档位和平台计划。
