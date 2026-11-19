# 多平台账号与授权执行计划

## 规划与开工门禁

- [x] 读取已完成的凭据研究合同，核对当前账号、OAuth DTO、刷新锁和实际 UI。
- [x] 用户确认复用现有链路接入 AGY，CC 接口及凭据返回保持兼容，回传收口独立处理。
- [x] 收敛 PRD、设计、范围、验收及依赖交接，准备完整 Brief。
- [x] 完整 Brief 取得有效批准后激活本任务，按 trellis-route 进入实现。

## 实施顺序

1. 新增平台及账号策略定义和后续登记迁移；同步 Account、存储读写、创建/更新 DTO、前端类型、字段差异提交及列表 SQL。
2. 建立平台分派和 CC 专用守卫，确保新增 AGY 账号的查询、去重、能力及维护隔离；缺省旧客户端继续取得 CC 行为。
3. 在现有 OAuthFlowService/接口中加入 AGY 分支，冻结平台、目标、代理与会话；实现最小原生 OOB 驱动、受信 runtime_bridge 及固定制品 staging。
4. 核验原生已认证身份和有效期，接回原账号保存/重授权流程；受控结束授权进程，清理和恢复均按同操作归属。
5. 复用 AccountService 锁、CredentialGate 和权威存储，完成 AGY 刷新状态、代次 CAS、原子提交、未知结果对账及重授权保护。
6. 从实际原生状态取得套餐、模型和额度的有来源数据；在现有账号界面接入平台筛选、能力及独立同形体开关。
7. 完成存储、服务、驱动替身、浏览器和跨层回归；真实原生 OAuth 单独验收并标识证据层级，模型调用为零。
8. 同步平台/凭据/策略合同给运行环境、同形体和请求记录子任务，进入 Check-All、Spec 评估及精确提交计划。

## 受影响位置

- gateway：model/account.rs、service/account.rs、service/oauth_flow.rs、service/oauth.rs、service/runtime_bridge.rs、handler/router.rs、store/account_store.rs、database_migrations.rs 及新增独立迁移定义。
- 隔离消费者：service/usage_poller.rs、service/telemetry.rs、service/native_runtime.rs 及真实调度/维护调用点，按引用搜索确认完整范围。
- orchestrator：新增 AGY 原生授权/刷新驱动及 main.py 的受信内部入口。既有工程/养号 LoginManager 保持原 CC 合同。
- 构建与验证：images/v3/Dockerfile、现有构建 staging、system_release.py 的迁移源映射、迁移回归及新增平台测试。原版二进制仅作私有制品输入。
- web：api.ts、Accounts.vue、已有表单差异及账号浏览器验证夹具，继续复用通用控件。

新增路径和签名由 design.md 定义意图；写代码前核对实际相邻定义、字段和调用关系。

## 验证矩阵

| 范围 | 必需场景 |
| --- | --- |
| 迁移 | 空库、旧版4升级、重复执行、同平台重复、跨平台同邮箱、历史重复冲突、原ID及权威凭据保持、旧程序兼容门禁 |
| 旧接口 | 缺省 CC 的新建/授权/列表、返回凭据合同、CC Setup Token、原内部列表及同步调用 |
| 平台隔离 | all/指定平台分页计数、未知值、平台修改拒绝、AGY 错入 CC 调度/刷新/遥测/额度路径拒绝 |
| 授权 | 两个平台、PKCE链接验证、代理修订、目标账号、错平台/错账号、重复码、超时/取消/重启/迟到结果 |
| 刷新 | 同账号并发唯一刷新、RT轮换/省略、代次CAS、响应丢失、写失败、rename后确认失败、锁失效后的持久pending、恢复材料归属 |
| 重授权和配置 | 原策略/绑定保持、并发配置差异保存、旧操作和旧授权回执隔离 |
| UI | 账号/平台切换、两账号开关独立、默认关闭、草稿/焦点保持、错误反馈及390px/桌面布局 |
| 原生验收 | 固定1.5.9、私有HOME、原生OOB、真实身份状态、RT回收、原生退出；模型提交0次 |

## 验证命令

实现后执行受影响模块规定检查：

```bash
cd services/gateway
cargo fmt --check
cargo test --locked
```

仓库根使用已存在依赖环境运行部署回归及新增驱动测试，固定当前工作树 PYTHONPATH：

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s deploy/flower2api
python3 deploy/flower2api/verify_database_definitions.py
npm --prefix apps/web run build
```

账号 UI 复用并扩展 verify_accounts_design.py，按影响面复用 verify_management_ui.py、verify_management_polish.py。迁移执行对应隔离 SQLite/PostgreSQL 的升级、重复执行、旧读写和 CAS 验证。新增验证入口已落地：

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python -m unittest discover -s services/orchestrator -p 'test_agy_auth*.py'
python3 deploy/flower2api/verify_agy_accounts_api.py
PYTHONPATH=deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python deploy/flower2api/verify_agy_accounts_ui.py
PYTHONPATH=deploy/flower2api /root/project/vibecoding-bench/.venv/bin/python deploy/flower2api/verify_account_filters_ui.py
```

API 验证须先 `cargo build --locked --manifest-path services/gateway/Cargo.toml --bin claude-code-gateway`。该验证启动独立回环网关和 SQLite，原生管理服务为合成替身，覆盖唯一刷新、重启、未知回执、错账号及原账号重授权。浏览器验证读取当前工作树正式构建。AGY 驱动测试使用真实文件锁与私有原生文件；固定原版启动/取消另有独立 Docker 实验。

PostgreSQL 使用任务专用临时容器，显式提供 `CCRB_TEST_POSTGRES_URL` 运行 `postgres_native_backend_migration_create_update_and_rollback -- --ignored`。该测试覆盖历史账号、跨平台同邮箱和 AGY 凭据代次事务。

真实原生 OAuth 在独立测试副本验证。本轮用户明确取消人工验收前置，后续运行环境任务或发布执行方在具备授权账号时补验。测试只进行账号状态、目录及刷新，付费模型请求数为零。需要人工授权码时保留原会话状态，避免重复创建或重放授权。

## 回退与交接

- 数据结构使用独立追加迁移，保持冻结基线摘要；完整账号和当前凭据逐项核验。
- 凭据未知结果先保持 reconcile，按同操作及当前私有材料恢复。清理范围只包括本任务明确创建的原生进程和私有临时目录。
- 向后续任务交付 platform、账号身份核验、刷新/发布代次、原生缓存限制、能力来源及同形体字段合同。
- 生产迁移、部署及付费模型调用分别进入对应授权流程。

## Check-All 四项修复与复验

- CHK-001：制品可用性、固定摘要和大小进入账号组件身份；真实签名与升级器双向切换回归。
- CHK-002：创建能力及时间落库；重授权、刷新、代理候选以同操作事务保存能力、凭据和代理。
- FBK-001：驱动先保存同账号、代次和操作的终止记录，再以CAS解除门禁。覆盖未落盘失败、重启及迟到RT请求拒绝。
- FBK-002：到期候选使用新代理执行一次原生刷新。恢复优先读取已落盘新RT，核对代理、身份及能力后原子提交。
- 定向证据覆盖驱动18项、存储5项、PG专项及真实网关HTTP；CC和AGY浏览器回归通过。完整证据见 research/implementation-validation.md。
- 真实Google授权、身份与刷新保留外部系统上线后验证。本轮按用户明确指示进入规范同步和提交计划，任务完成态由成功推送后的进度同步写入。
