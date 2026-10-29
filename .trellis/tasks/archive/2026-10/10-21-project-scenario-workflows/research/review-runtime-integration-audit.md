# Research: 私有评审运行原型接线审查

- Query: 只读审查当前私有评审原型，定位启动、隐藏材料、清理/释放、有限恢复和凭据刷新上的具体缺陷。
- Scope: internal；只读 `orchestrator/project_review_runtime.py`、`account_runtime.py`、`main.py` 及必要调用方；只写本文件。不改产品、规范、三件套，不运行容器、模型或产品测试。
- Date: 2026-10-21

## Findings

这是主会话持续实现期间的增量代码审查，不是最终实现验收。已即时向主会话发送高风险调用链；主会话完成的修正与仍待处理项分开记录。行号对应本次实际读取，后续编辑可能移动。

### AUD-01：私有 HOME 父目录不可写，driver 无法启动【P1，已核对修正】

- 原调用链：`ProjectReviewRuntime.start_run()`只对 `home/.claude`、`home/review`末级目录 chown1000，`root/home`仍由root拥有。容器UID1000，`images/worker/entrypoint.sh:144–164` 的 `patch_top_config_gates()`向 `$HOME/.claude.json.tmp`重定向写入并rename，在父目录权限处 EACCES；同一顶层文件也是CLI正常配置落盘位置。
- 主会话已添加 `os.chown(root/'home',1000,1000)`及0700（当前 `project_review_runtime.py:187–188`），本次已重读确认。
- 这里只确认权限修正进入代码；尚无真实Docker driver通过证据。

### AUD-02：正常 cleanup 先删除容器，release 再 inspect 已失效 exec【P1，已核对修正】

- 原调用链：`cleanup()`→`stop_container()`执行remove→`release()`继续 `exec_inspect(job['exec'])`。删除容器先销毁其exec上下文，会使严格释放转成错误，留下租约/执行记录与CLI隔离。
- 当前 `ProjectReviewRuntime.stop_container()`（`:270–283`）只stop/reload并持久 `review_phase='stopped'`；`AccountRuntime.cleanup()`（`:1773–1787`）先release，再尽力remove。本次已重读确认。
- 该修正覆盖正常收口；异常已经退出/消失容器仍有AUD-07的独立问题，不能据此认为所有重启路径已闭合。

### AUD-03：重评复用旧 protocol_error 可无限创建 Run【P1，已核对修正】

- 原调用链：首评保存 `job.review_result_json=protocol_error`，第二逻辑评审 `_reserve_run()`只改状态，未清旧结果。若第二Run在消费输入前失败，`job.review_attempt`仍1；`_settle_review()`看到上一Run的truthy旧错误，会再次设置review_ready，既不增infra恢复次数，也不增已消费逻辑attempt，反复创建Run。
- 主会话已新增每个 `project_task_executions.result_json`；`_capture_review()`写本执行结果；`_settle_review()`（当前 `project_scenarios.py:1184–1208`）仅取当前execution结果；新Run清空job当前摘要但保留历史执行结果。
- `_reserve_review()`现从最近执行的review_attempt恢复同一逻辑尝试，避免未消费的第二逻辑尝试退回第一尝试。本次已重读确认。
- 尚需主会话承诺的回归：首评protocol_error→二评消费前故障→有界infra恢复、逻辑attempt保持2、没有旧结果污染。

### AUD-04：本地刷新遇健康兄弟时丢失刷新待办【P1，已同步，待处理】

触发：未绑定cc2api账号，容量2，固定CLI中仍有健康candidate，review发现AT失效。

1. `Runner.watch_managed_oauth_refresh()`（`main.py:4187–4196`）识别原owner，先 `account_runtime.cleanup(worker_id)`，正确释放review shared holder。
2. 立即调用 `refresh_account_oauth_token(account)`。其v3分支（约`:4670`，原方法仍存在）调用 `claim(...,exclusive=True)`；`AccountRuntime.claim()`看到健康candidate sibling，直接RuntimeBusy，无法取得原刷新所有者的排他门禁。
3. watcher异常分支（`main.py:4213–4216`）再查刚cleanup掉的review token，必然过期，直接return。原刷新请求没有持久待办或明确刷新结果，`resume_required`也只在成功分支写。
4. review按infra恢复重新开始时仍取同一旧AT，可快速用尽两次infra机会并blocked；健康candidate持续执行本应只是暂时等待。

建议闭合：持久化绑定账号/身份/原source的owner刷新待办；review停止释放后，原owner在兄弟释放且门禁可得时刷新；成功发布最新合法凭据之后才允许继续原私有会话。等待不持review shared holder，不扣业务修正，也不能把pending刷新误报原账号永久认证失败。刷新失败事实不能因为原执行token已经失效而被吞。

### AUD-05：全表 review_ready 检查可阻塞所有账号的新候选【P1，已同步，待处理】

- `ProjectScenarios.drive()`（`project_scenarios.py:857–859`）在候选补位前执行 `SELECT id FROM project_evaluation_jobs WHERE status='review_ready' LIMIT 1`，没有账号、父批次状态/代次或review池可用性条件。
- 反例：账号A的批次暂停前留下review_ready。暂停批次自己在drive的状态门禁处返回，不会调度该review；账号B的正常批次也因这个全表存在条件返回，无法启动任何新candidate。只要A不恢复，B一直停滞。
- 同账号容量2、单review池已忙且另一个review_ready时，也会无谓阻塞本可与当前review并行的candidate。
- 应只为当前账号、当前可调度父代次、实际可用review池的ready工作保留下一槽位。候选优先级不得被不可调度或另一账号的记录锁住。

### AUD-06：claim成功后的第一次私有元数据保存不在try内【P1，已同步，待处理】

- `ProjectReviewRuntime.start_run()`（`:169–175`）顺序是 `claim`→`root_for_run`→`job.update`→`_save_execution`→`try`。
- 若root归属解析或第一次额外元数据持久写失败，已认领的job没有进入异常cleanup。Runner没有拿到返回token，无法通过sid/wid清理；若失败在赋run_id之前，`cleanup_quota_run(run_id)`也无法匹配该job。即使失败在后面的保存，内存job与磁盘已保存的普通claimed记录可能不一致。
- 影响是共享holder/私有pool被残留作业占住，下一次恢复的RuntimeBusy只能反复回队；不是普通一次启动失败。
- 建议claim返回后立即进入异常收口范围；可提前解析不带副作用的私有root/handle，再claim。任何成功认领后失败都必须使用已知完整token收口，持久意图失败不得留在途job。

### AUD-07：已经退出/被删除的review仍尝试在旧容器exec，重启无法收口【P1，已同步，待处理】

存在两个直接反例：

- **容器已因OOM或外部stop退出但仍存在**：`AccountRuntime.cleanup()`取得该容器后，无状态分派直接 `_cleanup_shared_job()`（`:1775–1777`）。job已有process时，后者调用 `control_execution('stop-job')`（`:1728`），进而对停止容器 `exec_run`（`:1696–1699`）；停止容器无法执行helper，异常先于stop_container/release发生。重启 `_reconcile_shared_executions`对review仍进同一路径，持续cli_reconcile。
- **容器已被删除**：`reviews.container(job,missing_ok=True)`返回None，cleanup跳过helper，但 `release()`（`:1164`）仍首先inspect旧exec；旧exec不存在时失败，仍留执行记录/门禁。

需要在review分支先reload和核精确容器：running才执行原监督进程控制；已经可信确认exited/created/不存在时，依据实际容器退出/消失事实封存旧进程状态、保留日志和source边界，再按幂等路径释放。未知/标签冲突仍阻塞，不能笼统捕获所有Docker异常当已清理。正常AUD-02的先stop后release顺序不能覆盖这两种异常终止。

### AUD-08：只有source登记、从未产生native输入时，infra恢复仍强制resume【P2，待主会话判定/补测】

- `execution_configuration()`（`project_scenarios.py:291–302`）以 `resume=bool(previous_sources)`判断原生会话是否存在；一条已预备source就要求native JSONL存在且有可核对对话。
- review先在 `ProjectReviewRuntime.start_run()`调用execution_configuration，之后才创建容器/exec/发ready。若这段出现启动失败，数据库已有source、尚无native文件；下一infra Run复用原session时无法通过“固定场景会话缺失”的检查，继续重试也不能自行恢复。
- 这不会无限执行，因为新计数已有上限，但会把可证明从未消费输入的一次启动故障转成永久受阻。应区分已有真实会话/输入与仅预留来源：若证据证明从未启动/未消费，可用同一个固定session ID进行首次启动；若任何实际消费/日志证明存在，继续保持严格resume和截断拒绝。不能仅为解锁而新建另一个session。
- 是否计时尾段应未知，须结合准备/启动许可证明判断。没有开始driver的source不能自动被当作已工作完整slice；不应为解决此点清零真实已消费预算。

### 范围内已核对的隔离接线

- 实际review分支位于 `AccountRuntime.start_run()`，运行角色由持久scenario context/Run读取；`_quota_mounts()`识别review后使用私有flows/control，未走共享 `execution_flows`。
- 子容器使用独立私有HOME/runs/jobs/drivers/input/access/flows，挂同账号network netns、只读CLI缓存/系统画像，未挂原home/projects/flows父树；UID1000、只读根、cap_drop ALL、no-new-privileges，沿idle+Docker exec监督器证明链。
- `run_session_path/run_artifact_path`已按持久Run角色定位私有根；管理端可读证据并不等于候选挂载可读。此次只读检查未发现把rubric、package或review transcript复制回候选HOME/共享flows的直接调用。
- 绑定账号watcher在活token和环境锁下定向 `reviews.sync_credentials(job)`，review凭据快照排除RT；原 `release`已排除review向管理profile回写凭据。未绑定账号的问题是AUD-04的待办丢失，不能通过让review持RT解决。
- 资源池有冻结布局检查、实际固定CLI Memory/MemorySwap/NanoCpus/Pids核对、单review内存预留和shared holder；本次未验证真实Docker资源合计或CLI峰值。

### 文件与规范依据

- 代码：`orchestrator/project_review_runtime.py`、`orchestrator/account_runtime.py`、`orchestrator/main.py`、`orchestrator/project_scenarios.py`、`orchestrator/project_evaluation.py`、`orchestrator/account_isolation.py`、`orchestrator/resource_budget.py`、`orchestrator/cli_quota.py`、`images/account/cli-control.py`、`images/worker/entrypoint.sh`。
- 规范：`.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`的共享source证明、唯一凭据所有者、真实收口、三角色权限与资源守恒契约；本任务`design.md`及`research/review-lifecycle-implementation-map.md`。
- 外部资料：本次无外部查询；Docker行为需主会话用本地真实隔离链路补证，本审查没有调用Docker/API/模型。

## Caveats / Not Found

- 主会话正在持续修改，AUD-04至AUD-08为写本文时观察到的状态；后续修复须重新读代码/回归，不能用本报告的静态结论替代验证。
- AUD-01/02/03只确认修正代码已出现，未运行相关产品测试，不代表最终验收通过。
- 未对所有新场景状态、内容质量、原生验收或完整UI/API/DB做最终审计；这些在本次子任务范围之外。
