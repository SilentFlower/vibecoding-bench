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
