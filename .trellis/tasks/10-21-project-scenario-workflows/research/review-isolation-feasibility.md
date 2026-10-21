# Research: 同账号独立评审容器的隔离可行性

- Query: 在既有 Scheduler／账号租约下，隔离评审 HOME、隐藏输入和原生日志，能否继续复用同账号网络、凭据身份与模型版本？
- Scope: internal；只读 AccountRuntime、Runner 及其账号容器创建依赖，不运行容器、测试、模型或 Git。
- Date: 2026-10-21

## Findings

### 1. 结论与最小可行边界

可以采用一种明确路径：**新增 project_review 专用的无特权执行子容器，复用原账号 network 角色的网络命名空间；通过现有 Scheduler 和 AccountRuntime 作业／租约登记管理**。
这不是当前已有配置开关；现有 `AccountRuntime.start_run()` 固定在账号 CLI 容器 exec，新子容器需要有限的生命周期分派扩展。
同账号指继续使用同一账号行、OAuth 身份、代理网络及模型／CLI 配置，不要求与候选共享 HOME、文件系统或 PID 命名空间。

### 2. 已核对的现有依据

- `orchestrator/account_isolation.py:191` 已把 CLI／sender 设置为 `network_mode='container:'+network.id`、`cap_drop=['ALL']`；这是可复用的网络挂接模式。
- 同文件 `:139` 的容器配置已有只读根、no-new-privileges、PID／内存／CPU 限额；网络角色独占 NET_ADMIN／TUN，CLI 不需要这些权限。
- 同文件 `:199`–203 表明当前候选能访问整份 home、projects、flows 及若干 runtime 子树；因此评审材料不能放入这些已挂载的共享源。
- `AccountRuntime.claim(row, account, source, idle_only=False, exclusive=False, shared_cli=False)` 位于 `account_runtime.py:1005`，支持共享 CLI 槽位及 `prepare-cli-shared` 账号租约。
- `_register_job()`、`_save_execution()`、`_heartbeat()`、`release()` 位于 `:236`、`:1115`、`:1172`、`:1138`，已有同环境多 source、持久登记、续租与释放能力。
- `Runner.start_run()` 在 `main.py:3987` 委托 AccountRuntime；不应让评审退回旧 worker／sidecar 分支，那会新建网络并绕开当前作业登记。

### 3. 子容器与挂载规则

1. 候选先封存并严格释放；评审仍由共享 Scheduler 占同账号 semaphore，经 normal 额度、时段、身份、父 generation 及准备后复查。
2. AccountRuntime 领取原环境的一个 shared_cli job／租约，再按已核验的环境与 network 容器 ID 创建评审子容器；不新增账号或独立网络代理。
3. 复用同批 account 镜像及精确 CLI 版本缓存；容器使用 UID1000、cap_drop ALL、no-new-privileges、只读根、独立 PID／mount namespace，不挂 Docker socket或任何设备。
4. 只挂评审专用 HOME、cwd、冻结评审输入、受控 driver、状态／日志与窄化凭据快照；临时目录单独 tmpfs。CLI 缓存、身份／系统画像和 resolver 可从核对后的只读源挂载。
5. 所有评审私有宿主目录放在控制端私有根，**不在原 CLI 已挂载的 home/projects/flows/runtime/runs/jobs/drivers/controls 下**；Docker 仅把所需私有子目录挂入评审容器。
6. 不使用原账号 HOME 的 `.claude/projects`，不把评审 transcript、driver 或隐藏输入复制回该 HOME，也不调用会产生共享兼容链接的默认 `_session_view`／`execution_flows` 路径。
7. 原生 usage／最终回复从私有评审 HOME 读取；被动额度采集只向受控路径写白名单事实，不能把隐藏对话作为“统计日志”放回候选可读的 `/flows`。
8. 退出后私有证据持久保留供管理端验收／恢复，候选只收到公开反馈投影；隔离依赖挂载和 PID 边界，不依赖删日志、隐藏路径名或提示词要求。

### 4. 同账号凭据与配置

- `sync_credentials()` 在 `account_runtime.py:837` 管理原权威 HOME，并在绑定账号时剥离 RT；`:864`–867 已有向网络侧发布 AT-only 快照的模式。
- 评审新增受控 AT-only 快照发布：从当前唯一合法所有者取同账号最新 AT及必要身份字段，白名单保留原 userID／OAuth 归属和冻结模型配置，不复制候选 hooks、项目历史或可写设置。
- 原账号身份、版本／effort／execution_model 保持；review HOME 是隔离运行副本，不能作为新登录环境，不能生成或写回新的账号身份，也不领取独立 RT 刷新所有权。
- 绑定账号仍由现有 managed watcher／cc2api 刷新，再定向更新当前评审凭据副本；`main.py:4150`、`:4208` 的路径解析和同步分派需扩展到私有容器。
- 未绑定账号仍由原 HOME／既有本地刷新所有者处理；`main.py:4656` 的刷新会认领 exclusive job，所以评审 AT失效时先释放评审作业，再由原刷新流程处理，不能持 shared_cli 租约内递归认领。
- 凭据不可安全更新或身份变化时保留私有评审现场并受阻；不让评审 CLI 自行刷新 RT，不复制未知凭据，不自动注册新账号。

### 5. 必须扩展的已有方法

- `AccountRuntime.start_run()` 增加评审专用执行分支；`_register_job/_save_execution` 记录原环境／generation／source与实际评审容器 ID、角色、私有产物根及创建意图，不能覆盖 `account_environments.container_id`。
- `wait_worker/control_execution/_cleanup_shared_job/cleanup` 当前通过固定 `_container(row)` 或原 jobs 路径控制进程（`:1553`、`:1590`、`:1625`、`:1661`）；需按 job 角色找到实际子容器并核验精确标签／代次。
- `release()` 必须先证明子容器停止且其全部进程退出，再退共享租约；失败沿 cli_reconcile，不停止健康兄弟或公共 network／sender。
- `reconcile/_reconcile_shared_executions` 当前强校验登记 container_id 等于固定 CLI（`:2733`–2757）；需识别新执行角色，重启按创建意图和精确标签收口遗留子容器，覆盖容器已创建但 ID尚未回写的崩溃点。
- `run_session_path/run_artifact_path`（`:1879`、`:1908`）、`Runner.read_worker_status`、managed refresh及用量读取必须定位私有评审证据，不能从原账号 HOME猜最近 session。
- 账号维护、删除、停止、容量／资源预算检查继续通过 `environment_jobs` 看见评审；每个子容器占既有 CLI名额，并计入既有账号／宿主资源上限，不因额外容器突破内存预算。

## Caveats / Not Found

- 尚无可直接创建该评审子容器的现成入口；可行的是扩展现有登记／租约和生命周期分派，不能只传一个新 cwd便声称隔离完成。
- 未做 Docker／真实 CLI 验证；挂载不可见性、独立 PID、同网络出口、私有会话恢复、额度采集和刷新交接需在后续隔离测试验证。
- 未绑定账号刷新交接和容器创建中断恢复必须纳入实现，否则该路径不能称为完整可恢复；本研究没有扩展账号、网络能力或容器特权。
