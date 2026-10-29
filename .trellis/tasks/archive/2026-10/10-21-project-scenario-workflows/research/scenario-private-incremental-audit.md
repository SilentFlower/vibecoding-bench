# Research: 私有评审生命周期增量审查

- Query: 只读审查私有评审的原凭据所有者刷新、冻结身份、孤儿子容器发现与准入、实际指标以及停止／释放恢复。
- Scope: internal；只读产品、任务三件套、相关规范与测试；只写本文件。没有调用真实模型、OAuth、Docker daemon 或生产服务。
- Date: 2026-10-21

## Findings

本次是主会话持续实现期间的增量研究，不是 Check-All 或交付通过证明。发现项均按本次实际代码记录；后续修正可能移动行号。根据 researcher 角色隔离要求，没有读取 implement/check JSONL。

### PRI-01【P1】：刷新待办没有绑定原 Run 身份，异步回调也绕开原 owner 锁和完整账号重读

实际调用链：

1. `main.py:4188–4195` 在未绑定私有评审收到刷新请求后，`defer_owner_refresh(job)` → cleanup → `retry_owner_refresh(account, runner.refresh_account_oauth_token)`。
2. `project_review_runtime.py:56–60` 用 `quota_identity(job['account'])` 生成待办身份。`main._quota_identity()` 在 `main.py:2828–2848` 读取当前管理 profile；没有使用 Run 已冻结的 `runs.quota_identity`，也没有存 run_id、source、environment generation 或原请求标识。
3. `project_review_runtime.py:82–95` 异步线程只查询 `SELECT enabled,deleted_at`；身份比较仍拿调用方的旧 account 字典，随后直接 `refresh(account)`。
4. `Runner.refresh_account_oauth_token()` 在 `main.py:4664–4700` 只持 profile 锁，不持 `_oauth_owner_lock`。原 `OAuthRefreshScheduler._tick()` 则在 `main.py:6009–6039` 先持 owner 锁、重读全账号、判断当前绑定，再调用此方法。新回调没有复用这层所有权门禁。

结果：原评审请求与当前 profile 已变化时，待办可能被直接绑定成新身份；若等待健康兄弟期间账号改绑，线程仍可把旧的未绑定账号快照传给本地刷新入口。完整绑定检查不能用 enabled/deleted_at 代替。

已运行无网络内存探针：传入 account.binding=None，而数据库最新行 binding=7；线程调用的 refresh 参数仍是 None，并把待办写成 complete。探针只调用真实 `ProjectReviewRuntime` 方法，文件读写与 refresh 是内存替身，没有刷新任何凭据。

建议：待办冻结原 Run 的 quota_identity、run_id/source、environment_id/generation；由 main 提供复用原 owner 锁的回调，在锁内重读可用账号、绑定和环境、核对冻结身份之后，才进入原 profile→environment 路径。变化时保留明确受阻原因，不能以新身份继续旧评审请求。写回待办也应核对仍是同一请求，避免旧线程覆盖后来待办。

可执行验证：用 Event 卡在待办线程准备调用刷新之前，另一线程按正式入口改绑／改名／停用；释放 Event，断言旧请求不调用本地 RT 刷新、不覆盖当前 profile，且保留旧请求原因。另覆盖当前 profile 身份与 Run.quota_identity 不同时 defer 直接拒绝。

### PRI-02【P1】：401 的强制刷新请求调用普通临期检查，可在没有刷新时被标成 complete

- `images/worker/entrypoint.sh:618–627` 的新私有评审分支来自 `force_refresh_profile_credentials_once()`；`1858–1868` 明确由实际 401／无效认证触发，request 带 `reason=worker_401`。
- `ProjectReviewRuntime.defer_owner_refresh()` 没保存 request 的 reason 或旧 AT 指纹；`retry_owner_refresh()` 在 `project_review_runtime.py:95–106` 忽略 refresh 的布尔结果，只要没有异常就标 complete。
- 普通 `Runner.refresh_account_oauth_token()` 在 `main.py:4676–4679` 遇到 profile 声称 valid 且 expiry 超过 buffer 时直接返回 False。这个条件不证明当前 AT 能通过刚发生的认证错误。

可复现条件：AT 的本地 expiry 仍较远，但实际认证已拒绝。新待办会不执行刷新却标 complete，恢复评审再次取得同一 AT；最后由有限 infra 恢复受阻，而非完成原所有者刷新。

建议：保留原请求 reason 及不含秘密的旧 AT 指纹；为这一原 owner 入口提供明确 force 语义，或确认已有其他 owner 已发布不同的新合法凭据后才完成。不要通过给评审 RT 来解决。

可执行验证：替身 OAuth status 返回 valid/远期 expiry，模拟私有评审 401；确认原 owner 发生一次强制刷新或复用已变化 AT，并在 token 未变化时保持受阻／等待，不能直接 complete。绑定账号的 `_sync_bound_account_credentials(..., force_refresh=True)` 是现有对照路径。

### PRI-03【P1】：新静态预留布局的真实指标仍按旧预算校验，且评审心跳采样固定 CLI

两处预算校验均仍使用 `isolated_account_limits()`：

- `AccountRuntime._sample_cli_metrics()`：`account_runtime.py:2695–2706`。
- `AccountRuntime.process_import()`：`account_runtime.py:2684–2690`。

新环境实际由 `scenario_account_limits()` 从固定 CLI 预算扣出 512 MiB 给评审。4 GiB 账号合计时，新 CLI 实际 3200 MiB，旧校验预期 3712 MiB。已用真实 `_sample_cli_metrics()` 和合成内核响应复现 ValueError：`实际 CLI 内存限制与角色预算不符`。这不是指标“未知”的正常情形，而是新布局无法采集／导入指标的确定回归。

此外 `AccountRuntime._renew_job()` 在 `account_runtime.py:1230–1238` 对任何有 version 的作业调用 `_sample_cli_metrics(row, _container(row))`。`_container()` 固定指向原 CLI，review 的实际 PID/cgroup 从未被取样；与 candidate 并行时，review 心跳会重复采样健康 candidate。当前异常被吞，所以正常链路模拟不会直接暴露此问题。

建议：固定 CLI 的预算依据已冻结、已核验的实际布局选择，两个入口保持一致；评审按真实执行角色选择私有容器与资源份额。若 canonical_process 仅保留固定 CLI 口径，至少明确排除 review 心跳，不把 candidate 样本归给 review；需要展示评审指标时独立记录其 role/container/source，不混进原 CLI 的 canonical 记录。

可执行验证：相同 4 GiB 账号分别使用旧布局和 scenario 布局，真实采样、API 导入分别接受 3712／3200 MiB；无布局却被外部改限额仍拒绝。让 candidate/review 各运行可识别进程，断言所读容器 ID、内存上限和指标存储归属准确；review 结束不改变 candidate 历史样本计数。

### PRI-04【P2】：无本地执行记录的实际 review 子容器不会在启动对账／正常准入中被发现

- `ProjectReviewRuntime.admission()`：`project_review_runtime.py:122–137` 只查刷新待办和固定 CLI 布局。
- `ProjectReviewRuntime.start_run()`：`project_review_runtime.py:269–273` 只从当前进程 `runtime.environment_jobs()` 判断单评审池。
- `AccountRuntime.reconcile()`：`account_runtime.py:2762–2767` 有逐执行文件时恢复；无文件分支 `2811–2842` 只核公共 network/sender/CLI 角色及 gateway lease，没有扫描实际 `project-review` 标签。
- 精确标签扫描存在于 `_stop_environment()`（`account_runtime.py:604–618`），但只在显式停机／维护等路径调用，正常启动准入不调用。

正常受控的创建意图已先于 Docker 创建持久化，因此“有完整记录、ACK 丢失”不是本问题。遗漏的是记录损坏／丢失、移除失败后遗留子容器等实际对象对账。已停止孤儿不会继续消耗运行 RAM，但会永久留存；若存在运行孤儿且原 holder 已过期，当前进程可在只看到空内存池时再创建新 review，破坏单评审池及静态资源份额约束。

建议：在环境锁内扫描本部署／本环境精确 `project-review` 标签，与磁盘创建意图和当前进程 job 一一核对；唯一、可证明归属的旧实例可以定向收口，未知／冲突则阻止新评审并提示对账，不能按名称猜测或停止健康公共角色。停止孤儿的删除可以尽力处理，不能把运行孤儿当空池。

可执行验证：真实创建仅带本次随机测试环境精确标签的 running review，然后删除测试专用 execution record 并重建 AccountRuntime；启动对账／新 review 准入必须阻止第二个子容器，健康 candidate/network/sender 保持。另测 exited 孤儿、同标签重复实例、跨部署同名实例，后者不能被操作。

### 本次确认已闭合的停止／释放代码路径

- 创建意图早于 Docker 创建，且 claim 成功后的持久化／建目录／启动均位于 try 内：`project_review_runtime.py:274–281,373–375`。此前 AUD-06 的 try 外 holder 泄漏已无直接代码路径。
- `AccountRuntime.cleanup()` 在 `account_runtime.py:1782–1800` 对运行私有容器先尝试监督器收口，失败后仍只停止这一个私有 PID 命名空间；已停止或不存在的容器不 exec helper。`stop_container()` 清 exec 并持久 stopped，之后 release，最后尽力 remove。
- `AccountRuntime.release()` 在 `account_runtime.py:1172–1187` 拒绝运行中的私有容器，且不会把私有 AT-only 凭据覆盖回原 profile；共享作业不等待独立 API。停止／缺失时旧 exec inspect 的已知问题已有针对性分派。
- `_reconcile_shared_executions()` 在 `account_runtime.py:2894–2916` 恢复 review 元数据并按 role 走同一 cleanup；不会把固定 CLI 当成 review 子容器停止。
- 私有容器按原账号 netns、独立 PID/mount、UID1000、只读根、cap_drop ALL、AT-only input/home/flows；本次没有发现将 package、rubric、review transcript 复制回 candidate HOME 的直接调用。

以上仅是代码审查确认，不替代下列真实恢复验证：创建 ACK 丢失、running／exited／missing 子容器、release 失败保留原 holder／记录、remove 失败但已 stopped、重启后定向回收、健康兄弟仍继续。

### 文件与规范依据

| 文件 | 本次用途 |
| --- | --- |
| `orchestrator/project_review_runtime.py` | 私有根、owner 待办、准入、创建意图、子容器资源与停止 |
| `orchestrator/account_runtime.py` | 原共享 holder、记录、心跳、指标、cleanup/release/reconcile |
| `orchestrator/main.py` | 稳定 quota_identity、owner 锁、watcher、原 RT 刷新与 scheduler 调用方 |
| `orchestrator/resource_budget.py` | 旧三角色预算与新静态评审预留 |
| `orchestrator/account_isolation.py` | 固定角色标签与 role_container 归属 |
| `orchestrator/project_scenarios.py` | review_ready 准入、持久 infra 有限恢复 |
| `images/account/cli-control.py` | UID1000 的实际 PID/cgroup sample |
| `images/worker/entrypoint.sh` | 实际 401→原 owner 刷新请求 |
| `deploy/v3/verify_project_scenarios.py` | 现有正常链路的资源／私有隔离断言；尚未覆盖本文反例 |
| `orchestrator/test_account_runtime.py` | 旧账号生命周期测试模式；本次搜索未发现 private owner/orphan 对应回归 |
| 本任务 `prd.md`、`design.md`、`implement.md` | R5–R8、AC5/AC7/AC9、设计第7–9节及原owner/严格释放契约 |

相关规范：`.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`（共享租约、唯一凭据所有者、三角色守恒、实际进程指标）、`project-iterations.md:84–110`（强阻断／严格释放／迟到代次保护）、`error-handling.md`。后者一般清理示例是旧 P1 语义；私有评审必须遵守更具体的严格释放证明，不能把吞异常当成已释放。

外部参考：本次没有查询外部资料；所有结论来自当前本地定义，Docker 故障行为仍需真实隔离测试补证。

### 本次探针命令与结果

环境：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=orchestrator .deploy/project-iteration-repairs/venv/bin/python`。仅调用真实 Python 方法，凭据读写／线程时序／刷新回调使用内存替身；没有写产品文件。

```json
{"probe":"scenario_cli_metrics","actual_mib":3200,"method_expected_mib":3712,"error":"实际 CLI 内存限制与角色预算不符"}
{"probe":"refresh_defer_identity","recorded":"current-profile-identity","frozen_run":"frozen-run-identity"}
{"probe":"refresh_latest_binding","database_binding":7,"callback_binding":null,"final_status":"complete","database_query":"SELECT enabled,deleted_at FROM accounts WHERE id=?"}
```

探针时源文件摘要：

```text
e823d8a1e42f1ac67f3433483fd2cdd0fb671c8f2f8706d26c566b82923d70ec  orchestrator/project_review_runtime.py
00bc47a4bd99e7e0840525f01a355d290a3bd5b8dbbfbe04a197652a34a93c21  orchestrator/account_runtime.py
a42228626300fde55dc5e0643f251a7ffbeb5003c69fe86d800d9680e7de58a1  orchestrator/main.py
```

## Caveats / Not Found

- 主会话正在修改相同源文件；本文描述的是探针及读取时刻，不能据此断言后续修复仍未完成。
- PRI-01 和 PRI-03 有无网络内存探针；PRI-02 是明确 401→普通刷新早退的静态调用链；PRI-04 是实际发现路径缺口，未创建孤儿容器验证。
- 没有运行产品 unittest、真实 Docker、浏览器或模型校准，也未修改任何产品／规范／三件套文件。
- 本研究未审完整场景状态机、内容评分质量、预算记账或原生回归；这些由主会话及其他专题覆盖。

## 复核增量：PRI-01～PRI-04 修正与刷新并发窗口

- Date: 2026-10-21；主会话修正后第二次只读复核。
- Scope: 保持原范围，不修改产品或规范；无网络内存探针补充，不冒充真实 Docker／OAuth 验收。

### 已确认的修正

- **PRI-01**：`defer_owner_refresh()` 现从原 `runs.quota_identity` 冻结身份，同时保存原 environment generation、run_id、source 和 request_id。待办线程重读完整账号及环境代次。`main._refresh_project_review_owner()`（本次约 `main.py:7766–7791`）持原 `_oauth_owner_lock`，再次重读账号／环境并通过待办冻结身份检查，然后才选择原绑定 owner 或本地 owner。原来旧未绑定字典直接进入本地刷新的路径已替换。
- **PRI-02**：原刷新方法、容器探针及其脚本已贯穿 `force_refresh`，本地状态及脚本中的远期 expiry 早退均显式排除 force；新 callback 要求本地刷新确实返回 True。只加 Python 参数而脚本仍 skipped 的旧问题没有残留。
- **PRI-03**：`_sample_cli_metrics()` 与 `process_import()` 均在存在冻结布局时通过 `reviews.check_layout()` 取真实 CLI 份额；心跳按 execution_role 分派到私有 `sample_metrics()`，后者只写私有根。已重复调用真实 `_sample_cli_metrics()`，新 3200 MiB 响应得到接受。
- **PRI-04**：`check_orphans()` 扫描精确 deployment/environment/role 标签，与内存及磁盘创建意图核对；已经接到 admission、实际 start_run 和启动 reconcile。无登记运行实例阻止准入，已停止且精确归属的实例可尽力删除。

### 复核期间额外发现、已即时修正的两处问题

1. **同一 request 已完成后，被旧 retry 快照再次认领**：原修正版在锁外读 state，再认领 `_refreshing`；若另一线程恰好把相同 request_id 写 complete 并清除 `_refreshing`，本次线程会把 complete 再改 refreshing，request_id CAS 无法识别同请求已收口。本次最初探针确实观察到 callback_count=1、writes=[refreshing,complete]。主会话已在 `_refresh_lock` 内重读 state，并在线程真正处理前再次拒绝 complete/error／不同 request_id；重新跑相同交错，callback_count=0、没有写入。
2. **历史 complete 待办在合法换身份后错误阻塞**：原 `owner_refresh_state()` 先比 identity 再忽略 complete。主会话已把 complete 的返回放在身份检查之前；最新探针确认旧身份的已完成记录返回 None，不干扰新评审。

### 本次最新探针结果

所有文件读写、refresh 回调、Docker 接口均为内存替身；真实调用当前 `ProjectReviewRuntime`／`AccountRuntime` 方法。main callback 为从当前文件 AST 提取出的真实函数体，避免导入整服务产生额外副作用。

```text
same_request_completed_before_claim: callback_count=0, writes=[], final_status=complete, return=False
late_completion_preserves_new_request: callback_count=1, writes=[refreshing], final_status=waiting, request=c
completed_old_identity: returned=None
owner_callback_force_under_lock: refresh_count=1, force_refresh=True
orphan_running: blocked, remove_count=0
orphan_exited: allowed_after_cleanup, remove_count=1
scenario_cli_metrics_corrected: actual_mib=3200, accepted=True
```

`late_completion_preserves_new_request` 在旧 callback 返回前用替身模拟新 request 已落盘，旧线程的最终 complete/error 写回均未覆盖它。这个探针验证 request_id CAS 的写回保护，不代表授权请求可以绕过原 owner／环境锁自由换代。

本次最后读取 `project_review_runtime.py` SHA256 为 `93671604ccb81433d8b4808d2d6da518fee8132846d6088f354545742f0ba071`。在上述限定范围内，当前未再发现明确的 P1 竞态；仍需正式单元回归及真实 Docker 故障验证证明运行行为，尤其是创建 ACK 丢失、原 holder 释放失败、旧容器缺失／停止、健康兄弟保持及跨重启恢复。

## 复核增量：重授权／重建后的旧待办跨代阻塞【PRI-05，P1，已复现、未改产品】

- Query: 旧 owner refresh journal 为 waiting/error，正式重授权已产生新身份，或显式空闲重建后已进入新 environment generation；新批次是否仍永久继承旧请求失败？
- Date: 2026-10-21。
- Scope: 读取正式登录提交、维护重建、原 journal 与新场景准入路径；仅用内存 SQLite、无网络回调及 Docker／文件替身取证，不运行真实登录或重建。

### 明确结论与调用位置

**当前仍会跨代阻塞。** 上一节 complete 历史记录的修正只覆盖 complete；waiting/error 残留没有退出当前账号级准入的路径。该结论不改变原请求应拒绝刷新新身份的正确性；缺陷是原请求的拒绝被提升成新身份／新环境的永久账号级禁用。

- `owner_refresh_state()`（`project_review_runtime.py:42–50`）：只忽略 complete；身份不符时返回 error，但原 waiting 文件保持；error 也始终返回。
- `admission()`（`:159–162`）：上述任一 error 立即 blocked，不核对该请求是否属于新评审的 scope，也没有归档入口。
- `retry_owner_refresh()`（`:87–89`）：error 直接 False；同身份但旧环境 waiting 则在线程 `:124–125` 检测 generation 不符，随后 `:141–143` 写 error。此后不再重试，没有刷新新环境，但新 admission 仍被 error 阻塞。
- `defer_owner_refresh()`（`:72–78`）：旧 waiting/refreshing 与新身份或代次不符会拒绝；旧 error 允许替换，不过新评审已被 admission 拒绝，所以这个内部替换能力不是实际自愈路径。
- `AccountRuntime.claim()`（`account_runtime.py:1030–1034`）会让同 scope waiting 继续占住普通 run/continue 的后续准入；重授权及 maintenance 的 source 前缀不受这一分支限制，因此用户可以完成正式修复，journal 却仍存留。
- `ProjectScenarios.drive()`（本次约 `project_scenarios.py:949`）先 retry owner；`_reserve_review()`（约`:1316`）再 admission。因此旧 generation waiting 会先被收成 error，然后新评审被判 blocked，而不是调度器忘记 tick 的暂时等待。

正式流程没有清理这份账号级 journal：

1. 未绑定登录提交在 `main.py:10029–10038` 清旧 quota 状态／游标并 `commit_login()`；`AccountRuntime.commit_login()`（`:2196–2214`）只镜像合法登录文件与环境归属，没有 journal 失效处理。
2. 绑定重授权完成走 `finish_bound_login()`（`account_runtime.py:2332–2373`），更新已经验证的凭据与 oauth 身份、发布 mirrored，也没有 journal 失效处理。
3. 正式维护路由 `main.py:12018–12040` 已持 owner→profile→environment 锁。`AccountRuntime.maintenance(...,'rebuild')`（`:2532–2553`）收口并删除本环境容器、释放维护门禁、只删除 `runtime/execution.json`、置 stopped，没有触及独立数据根下 `project-review-owner-refresh/<account_id>.json`。
4. rebuild 本身不增 generation；后续 `create_environment()`（`account_isolation.py:122–123`）才提交 generation+1。因此准确场景是“成功空闲 rebuild，再正式创建新环境代次”。

### 无网络内存 SQLite 矩阵

使用真实 `ProjectReviewRuntime.owner_refresh_state/admission/retry_owner_refresh/defer_owner_refresh`。accounts、account_environments、runs 放 SQLite `mode=memory&cache=shared`；journal 读写放内存字典，线程同步执行以固定交错；刷新回调为计数替身。每项独立恢复初态，defer 测试不会污染 retry 测试。

| 正式操作后的状态 | 旧 journal | admission 初值 | 对新请求调用 defer | retry 后 | 新 admission |
| --- | --- | --- | --- | --- | --- |
| 新 identity，旧 env gen3 | waiting | blocked=true | 拒绝：其他身份待办 | False，0 次刷新，文件仍 waiting | blocked=true |
| 新 identity，旧 env gen3 | error | blocked=true | 内部允许替换，但外层准入不可达 | False，0 次刷新，文件仍 error | blocked=true |
| 同 identity，新 env gen4 | waiting(gen3) | 暂时 waiting | 拒绝：其他身份待办（实际是代次不同） | True，0 次刷新，文件写 error | blocked=true |
| 同 identity，新 env gen4 | error(gen3) | blocked=true | 内部允许替换，但外层准入不可达 | False，0 次刷新，文件仍 error | blocked=true |

另调用真实 `AccountRuntime.maintenance(...,'rebuild')`，只替换 Docker 调用、锁及文件 unlink，数据库查询仍为真实内存 SQLite：观察 `_stop_environment(remove=True)`，只 unlink `runtime/execution.json`，未读写／删除 owner refresh journal，maintenance 后 generation 仍为3，与源码路径一致。

没有实际重新授权或创建容器；矩阵模拟的是这些正式流程成功后的、由现有真实定义确认的身份／代次后置状态，不能据此声称 OAuth 或 Docker 全链已跑。

### 最小安全修复契约

1. **失效的是旧请求，保留的是旧业务结果。** 正式重授权成功／新环境代次受控发布时，在现有 owner→profile→environment 锁和 journal 锁下，对旧 scope 的原 request_id 做 CAS，归档／标记 `superseded`（或等价的明确取消终态），记录旧身份／环境、原错误、原因和时间。不能伪造为“刷新完成”，不能重置旧任务、旧预算或旧批次结果。
2. **账号级准入只关联当前 scope。** 真实当前身份＋environment_id/generation 下尚未收口的待办才可等待或阻断当前工作。已被正式替代的旧请求留历史，不阻断新批次；旧请求也绝不能把 scope 改成当前新身份后继续刷新。`defer` 遇到旧 scope 时应复用同一受控失效／归档 helper 后创建新 request，而不是直接覆盖未确认活动待办。
3. **迟到线程不能复活旧请求或误处理新请求。** 旧线程写回除了 request_id，还须拒绝覆盖 superseded／已取消终态（或使用修订号／认领 token CAS）。main callback 应接收并核对“本次期望 request_id＋冻结 scope”，不能只按账号读取最新任意 journal：否则旧线程在等待 owner 锁时发生正式修复并出现新待办，可能误把新待办当成自己要刷的请求。旧回调必须退出，旧写回必须失败且不污染新记录。

若采用纯 reader 过滤旧 scope 的最小实现，也必须让原刷新 callback 与写回都绑定旧 request_id/scope，并在受控状态下保留“已被正式替代”的可审计事实；不能仅 `return None` 后让迟到旧线程继续刷新。坏记录、身份暂时不可读、环境不存在或仍有旧 holder／进程时继续阻断，不能把不确定性当成“已经正式换代”。

建议补充自动回归：上表四项；同身份成功重新授权用于修复 error；修复／新 journal 与旧 callback 在 owner 锁处交错；旧线程晚写 complete/error 不复活 superseded；未完成 reauth／rebuild 不能提前解除旧门禁；新批次通过而旧批次保持原 blocked／cancelled 及成本不变。

### 本轮读取摘要

```text
93671604ccb81433d8b4808d2d6da518fee8132846d6088f354545742f0ba071  orchestrator/project_review_runtime.py
3c850cda7979bc12d44ffef07e9b10c315a064836bbb73fad0cb3203c2c0f9d8  orchestrator/account_runtime.py
113e4ea62b551305217d80cc1ab8ef89307f2767e32e6098287a1074f0418b50  orchestrator/main.py
```

## PRI-05 修后定向复核：scope、归档、双参数 callback 与迟到写回

- Date: 2026-10-21。
- Scope: 只读当前 `project_review_runtime.py` 与 `main.py` 对应刷新函数及实际调用入口；只运行新的无网络内存 SQLite 探针，没有重跑旧全套、Check-All、真实 OAuth 或 Docker。

### 当前实现核对

- `owner_refresh_state()`／`_refresh_applies()`（`project_review_runtime.py:36–69`）以当前 identity、environment_id/generation 和被拒 AT 摘要界定待办作用范围。身份或环境代次已变化，或原 owner 已发布不同且仍有效的 AT，旧待办不参与当前准入。相同有效上下文的 error 仍返回，保持有界失败门禁。
- `defer_owner_refresh()`（`:71–112`）先校验原 Run 冻结身份、数据库当前账号及环境代次，读取当前私有作业实际被拒 AT；新 request 与旧 request 不同时，只有旧请求已经完成／失效或不再适用，才将旧记录写 `archive/<old_request_id>.json`，状态为 superseded，并保留 previous_status、superseded_at、replaced_by，随后发布新 request。归档没有把旧失败伪造为刷新成功。
- `retry_owner_refresh()`（`:137–174`）在调用前保留当前 request，并以 `refresh(account_now,current)` 传两个参数；旧写回仍核对 live journal 的 request_id。当前 superseded 由归档副本表示，live journal 被新 request_id 替换，所以旧线程不能覆盖新 live 请求。
- `main._refresh_project_review_owner(account,request)`（本次 `main.py:7766–7794`）持原 owner 锁，重读可用账号／环境，重新计算当前适用待办，并逐项比较原线程 request_id、identity、environment_id/generation 后才强制刷新。旧 callback 不能把当前新 journal 当作自己要处理的请求。
- 搜索实际调用入口：watcher（`main.py:4197`）、manager callback（`:7923`）、本地真实链路 harness（`deploy/v3/verify_project_scenarios.py:115`）均将该双参数函数交给 `retry_owner_refresh()`，没有发现产品入口还直接按单参数调用 main callback。测试里的 Mock 回调不构成产品调用契约。

### 新探针结果

SQLite 使用内存共享连接，accounts／account_environments／runs 的定义与当前查询完全匹配；journal/profile/private access 通过内存文件映射替身读取。调用真实 `ProjectReviewRuntime` 方法；布局检查与容器接口替身仅让 admission 到达所审的 owner 门禁，不声称真实资源验证。

| 变化 | 旧 journal | 新 admission | 旧归档状态／previous_status | 新 journal |
| --- | --- | --- | --- | --- |
| identity old→new | waiting | allowed=true | superseded／waiting | waiting |
| identity old→new | error | allowed=true | superseded／error | waiting |
| environment gen3→4 | waiting | allowed=true | superseded／waiting | waiting |
| environment gen3→4 | error | allowed=true | superseded／error | waiting |
| owner 发布不同的有效 AT | waiting | allowed=true | superseded／waiting | waiting |
| owner 发布不同的有效 AT | error | allowed=true | superseded／error | waiting |

另三个反例：

```text
same_rejected_scope: blocked=True
late_write_cas: callback_args=2, new_request_preserved=True, status=waiting
late_actual_main_callback: rejected=True, refresh_calls=0
```

`late_write_cas` 在原 callback 返回前，实际调用新 `defer_owner_refresh()`，模拟 owner 已发布新 AT 并创建新 request；旧线程完成／异常写回未覆盖它。`late_actual_main_callback` 从当前 main 文件 AST 提取真实函数体，向当前新 journal 投递旧冻结 request，确认进入原 owner 刷新前即拒绝，且没有执行任何网络调用。

结论：PRI-05 的四个既定反例及新增 token 作用范围已在该限定机制下解除；当前未发现新的明确串代或永久阻塞。未通过本文操作恢复旧任务、改写旧结果、清空旧预算，也未运行真实重授权／重建，因此最终真实生命周期证据仍由主会话验证负责。

本次读取摘要：

```text
b0222a72eb757c79b9f1d3a83c17766aebd2e8825bc626f7ee6d0d27641c388f  orchestrator/project_review_runtime.py
23dcce860c5da6ecdc4e380844be7d15884890e0aecde5ec993507ba59ac46c0  orchestrator/main.py
```
