# 登录草稿转正式账号的额度挂载调查

## 已核对的链路

1. `login_drafts.py:206` 的草稿配置只有名称、时区和原代理，没有正式账号 ID。
2. `account_isolation.py:184` 只在 `account.id` 存在时创建 `/quota-accounts/<id>` 的只读目录挂载。挂载在创建网络容器时固定。
3. `account_runtime.py:2234` 的 `commit_login()` 通过 `_row()` 绑定账号并镜像 HOME，不改变三角色容器。
4. `_row()` 在 `account_runtime.py:294` 只更新 `account_environments.account_id`。后续 `ensure()` 在角色完整时复用容器。
5. `pi_terminal.py:125` 的完整抓包上下文要求 `/quota-accounts/<id>/state.json`；Recorder 的观察线程读取失败后写暂停信号，监督器返回 43。

线上 11-5 的实际 Docker Mounts 为空、容器内路径不存在，宿主额度状态正常。通过原维护重建后，网络容器加入本账号只读目录，同一任务和会话产生真实正常模型响应。相关证据在 `.deploy/11-5-quota-repair-20261106/`；`account_runtime.py` 与 `account_isolation.py` 的线上／本地 SHA256 分别为 `241da5ffd6f2d8bb16822ee37bbebec93070d4e8cb029f3c5e845212310a9c62`、`121e530a6267d0704c3ad2d24926d65973b2605f7e2dba57d8986a1ad9fd54a9`。

## 可复用的既有保护

- `AccountRuntime.maintenance(environment_id, 'rebuild')`：在环境锁中使用 `claim(..., idle_only=True, exclusive=True)`，核对活动／等待 API、CLI、发送器和评审交接，再定向停止移除本环境三角色。
- `claim()` 使用不可复用 source 和既有网关维护租约，拒绝兄弟执行；临时占用沿 `RuntimeBusy` 处理。
- `_stop_environment(remove=True)` 保留持久目录和画像；`create_environment()` 用正式账号 ID 创建所需挂载。
- `_execution_records()` 校验持久共享执行目录、链接及数量。自动补齐前还须检查原单执行登记，不能覆盖遗留记录来认领维护。
- 新角色创建中断时原实现逐个登记、停止本代实例并保留 `reconcile`；不得自行擦除这些证据。

## 方案比较

| 方案 | 影响 | 结论 |
| --- | --- | --- |
| 为单账号挂载整个全局额度根目录 | 会暴露其他账号状态 | 排除 |
| 向环境目录复制第二份额度状态，并修改全部发布与消费路径 | 引入双份事实、迁移及原子发布问题 | 本次不采用 |
| 登录提交时立即销毁原登录容器 | 侵入原 SID／清理／失败重试顺序 | 本次不采用 |
| 正式账号实际 `ensure()` 时检查挂载，遗漏时经既有空闲维护重建 | 保持原路径和发布者，兼容历史遗漏，可复用维护门禁 | 采用 |

补齐只适用于布局 2 且挂载明确缺失的正式账号；错来源、可写、其他账号挂载或坏观察均失败关闭，不当作普通缺失。未提交草稿和状态 GET 不进入补齐。

## 回归入口

- `orchestrator/test_account_runtime.py` 有三角色 Docker 替身 `_isolated_docker()`，适合断言真实创建参数、生命周期和保护分支；当前替身没有提供实际 Mounts，需要补充与 Docker 相同形状的元数据。
- `orchestrator/test_login_drafts.py` 已覆盖提交失败、重试和草稿隔离，但使用单容器替身，没有覆盖草稿绑定后网络目录。
- `deploy/v3/verify_login_drafts.py` 已经通过真实浏览器、HTTP、SQLite、三角色容器走完无 ID 草稿到正式提交。应在提交成功后增加首次正式准备、实际挂载读取及 Recorder 额度观察断言。
- 该场景由既有命令 `python3 deploy/v3/verify_stack.py --manifest <本地清单> --source-overlay --browser --reauth` 调用。已有 `.deploy/v3-ownership-implementation/release-a6.json` 为本地 dirty 清单，相同标签的 control/account 镜像在当前 Docker 中均存在；仅可作为本地源码覆盖验证，不作为正式发布证据。

## 规范依据

- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：登录草稿、三角色隔离、空闲维护、身份及资料保留。
- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md`：账号专属只读额度状态和门禁故障关闭。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md`：原工作／会话及启动失败保留。
- `.trellis/spec/vibecoding-bench/frontend/hook-guidelines.md`：登录提交失败后的恢复和终端生命周期；本次保持 UI 契约。

以上为规划阶段由主会话完成的调查记录；当时尚未修改产品代码。

## 实施复核：API 准备不能等待排空自己

- `cc2api/src/service/gateway.rs` 在调用 `runtime_transport::prepare()` 前已通过 `acquire_v3_admission()` 获取账号并发许可。
- `cc2api/src/service/runtime_transport.rs` 的内部请求最终进入 `AccountRuntime.transport()`；网关 lease 状态中的 active 包含当前请求持有的许可。
- 因而独立 API 若在该入口补建 CLI 专用额度挂载，会在维护空闲检查中阻断自身。`transport()` 固定传 `require_quota_mount=False`，仅允许明确缺失时继续复用；错误或不可核验的挂载仍拒绝。CLI 及其它准备沿默认 true 补齐。

## 根因与防再发

这属于账号生命周期转换时遗漏容器资源合同：数据库绑定正式 ID 不会改变 Docker 创建时固定的 Mounts。原草稿测试覆盖提交与恢复，运行时替身却没有实际 Mounts，也没有验证正式保存后的首次抓包，因此两个局部分支分别通过仍漏掉连接处。

修复在实际环境复用与新创建后都验证挂载事实；回归从无 ID 草稿开始绑定，既核对真实形状的 Mounts，也通过现有浏览器／HTTP／SQLite／Docker 链路读取额度文件、验证只读和 Recorder 观察。持久合同由后续 Update-Spec 写入现有账号运行环境规范。
