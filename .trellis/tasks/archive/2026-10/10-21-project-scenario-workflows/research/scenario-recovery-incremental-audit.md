# Research: 新场景恢复路径增量审查

- Query: 完整候选／评审输出遇 quota_wait 是否重复调用模型，严格释放错误的阻断范围，业务尝试收尾，以及逻辑计划和项目轮换是否闭合。
- Scope: internal，只读代码与内存状态探针；不调用模型、不操作真实账号、不编辑产品或规范。
- Date: 2026-10-21

## Findings

本次审查与主会话实现并行。下述“已加入修复”只表示读到了对应代码，不能替代主会话的单元与真实 Docker 验证。引用行号以本文件建立时的源码为准；后续实现可能移位，函数名与条件才是稳定定位点。

| 编号 | 结论 | 审查时状态 |
| --- | --- | --- |
| REC-01 | 完整输出后的 quota_wait 原先会重复投递模型 | 主会话已加入 `finish_captured_quota()`，仍需候选／评审双角色回归 |
| REC-02 | 严格释放失败原先只阻塞任务，quota_wait 下甚至绕过处理 | 主会话已加入批次阻断及 quota 前置错误分派，仍需恢复竞争验证 |
| REC-03 | 业务尝试从不写 ended_at/result，历史一直显示开放 | 主会话已补部分收尾；`_block_evaluation()` 的 CAS 成功分支仍须一并处理 |
| REC-04 | 分支激活的新任务可遮挡逻辑计划内就绪任务，导致永久停滞 | 内存 SQLite 已复现；主会话已加入计划成员过滤，需回归 |
| REC-05 | quota_wait 写入后、释放证明持久化前崩溃，完整输出恢复永久等待 | 已用真实方法调用复现；恢复器须补严格清理与来源释放事实 |
| REC-06 | 场景结束、超时耗尽及评测受阻未统一触发项目访问轮换 | 设计完整性缺口；不会直接造成上述计划死锁，但需按既定契约统一 |

### REC-01：完整输出只续验收，必须覆盖两个调用入口和两个角色

原路径：

1. `capture_submission()` 已持久化 `project_evaluation_jobs.status='waiting_release'`，或 `_capture_review()` 已保存执行级 `result_json`。
2. Scheduler 因额度中断把原 Run 写为 quota_wait，并在 finally 清理后调用 `execution_released()`。
3. 原 `drive()` 只处理 running 与 success/failed/timeout/stopped/auth_failed，不处理 quota_wait；`recover()` 也直接跳过 quota_wait。
4. `QuotaGuard._resume_waiting()` 通过 `ProjectIterationManager.execution_allowed()`，增加额度代次并提交原 Run。
5. `execution_configuration()` 对 `quota_attempt > 0` 无条件新建 continuation 投递并启动 CLI，同一完整答案被再次询问。

定位：`orchestrator/project_scenarios.py:317`、`orchestrator/project_scenarios.py:787`、`orchestrator/project_scenarios.py:875`；`orchestrator/main.py:3667`；`orchestrator/project_iteration.py:327`。

主会话已新增 `finish_captured_quota()`，由项目 tick 与 QuotaGuard 两边调用，核对当前 source 后关闭模型恢复路径。当前实现将真实额度中断保留为 failed，并由独立验收判断任务结果，没有伪写 success。

所需反例：候选已封存、评审有效 JSON 已封存、评审 protocol_error 已封存，三种情况都不应出现新的 source／输入消费或新模型执行；普通未完成额度等待仍须沿原 Run/session 恢复，不能误判已完成。封存证明属于旧 source 时不能抑制当前未完成来源。

### REC-02：严格释放错误是更强批次门禁，不由是否已有完整回答决定

原 `_settle_execution()` 看到 `source.execution_error` 只执行 `_task_status(...,'blocked')`，与既有“严格清理失败阻断批次”契约冲突。更严重的是 quota_wait 根本不进入 `_settle_execution()`；即使存在清理错误，`execution_allowed()` 只检查父状态、generation 与 execution.ended_at，仍可能进入下一额度代次。

主会话已加入：

- `_settle_execution()` 对真实严格释放失败调用原 `_batch_error()`；计时／原生日志边界无法核实仍作为局部任务受阻。
- `finish_captured_quota()` 在判断 captured 之前先处理 source.execution_error，覆盖“没有完整输出但清理失败”。

定位：`orchestrator/project_scenarios.py:806`、`orchestrator/project_scenarios.py:1085`；Scheduler finally 的真实释放通知位于 `orchestrator/main.py:7053` 附近。

所需反例：候选／评审各自的完整与未完整输出 × terminal/quota_wait；错误后父批次 blocked、generation 增加、兄弟执行受控停止、无新额度代次。计时尾段 uncertain 应保留预算，不冒充物理进程仍存活，也不自动改成业务失败。恢复与实际提交 CAS 之间仍须保持原父门禁复查。

### REC-03：业务尝试关闭点必须与业务决策对应

`project_task_attempts` 定义含 ended_at/result，但审查开始时全模块只有 INSERT/SELECT，没有任何 UPDATE，因此已通过任务的 attempts API 仍返回开放尝试。

主会话已补：

- `_task_status()` 写入终态时关闭开放尝试。
- timeout 开始新的业务继续前关闭旧尝试为 timeout。
- `_apply_result()` 的 pass、fail/correction 或最终耗尽关闭当前业务尝试；普通 disclose 保持同一尝试。

仍需核对 `_block_evaluation()`：该函数直接通过 CAS 将任务改为 blocked，未调用 `_task_status()`。合法 uncertain、评审预算耗尽、原生验证环境错误都可走这里；应在任务 CAS 真正成功的同一事务关闭该任务的当前开放尝试。不能因旧 job 迟到而关闭新业务尝试。

定位：`orchestrator/project_scenarios.py:594` 的输入消费与认领；`orchestrator/project_scenarios.py:1085` 的收口；`orchestrator/project_scenarios.py` 的 `_block_evaluation()`、`_apply_result()`。

注意：不能简单在每个 candidate Run 结束时关闭业务尝试。澄清、quota 与基础设施继续共享尝试；新业务尝试仍须等真实输入消费后才建立。

### REC-04：新激活任务遮挡冻结计划内任务

反例是合法的可达分支内容：

1. 场景按展示顺序包含 Q1、Q2、Q3；初始只选择 Q1、Q3。
2. 首个逻辑计划冻结 `[Q1,Q3]`。
3. Q1 合理澄清时披露分支，激活 Q2；随后 Q1 通过。
4. 原 drive 用 `ORDER BY t.id LIMIT 1` 选择 Q2。
5. `_plan_for_task()` 因 Q2 不在开放计划中返回 None，而 drive 不再尝试 Q3；下个 tick 重复相同行为，Q3 永远无法执行，计划也无法结束。

已用真实 `initialize_scenario_schema()`、内存 SQLite 和 `_plan_for_task()` 运行以下状态探针；没有模型、文件或 Docker 参与：

```json
{"initial_plan":[1,3],"selected_ready_task":2,"reservation_plan":null,"remaining_plan_task_status":"ready"}
```

最小修复是候选选择时排除“不属于该场景已开放计划”的任务，先完成冻结范围，再建立新计划。主会话已加入 `json_each(p.task_ids_json)` 的成员过滤，见 `drive()` 的 ready 查询。动态激活不应修改已冻结计划，也不能把材料披露本身计成任务通过。

所需回归：上述 Q1 披露并通过后，下一个选择为 Q3；Q3 结束后原计划 completed，再执行 Q2；重启后顺序及任务集合不变。还应保留 DAG 拓扑选取与轮换余量 2+2+1 的回归。

### REC-05：quota_wait 收口崩溃窗口造成双方等待

该问题出现在 REC-01 的新门禁与既有恢复跳过规则组合之后。

可复现顺序：

1. candidate evaluation job 或 review result 已完整持久化。
2. Run 已持久化 quota_wait。
3. 控制端在 Scheduler finally 的 `execution_released()` 前退出，source.released_at 与 execution_error 均为 null。
4. 启动后 `recover()` 因 quota_wait 直接 continue，未调用 cleanup，也未补来源释放事实。
5. `finish_captured_quota()` 因 captured 且尚无 released_at/error 返回 True，阻止 QuotaGuard 重启；drive 也不能 settle 未释放来源。
6. 每次 tick 重复，候选永久 waiting_release。实际旧容器即使已由运行时对账清掉，缺少业务来源释放事实仍无法推进。

使用当前真实 `recover()` 与 `finish_captured_quota()`、受控持久行和可观测 cleanup/_write 调用，得到：

```json
{"restart_cleanup_calls":[],"finish_captured_quota":true,"state_updates":[],"source_released_at":null}
```

最小修复建议：恢复器不能仅因 quota_wait 跳过未证实释放的来源。对该来源仍调用原严格 cleanup，再调用 `execution_released(run_id,quota_attempt,error)`；保持 quota 中断事实。完整输出随后只续验收，未完整输出才允许原 Run 的下一额度来源。若无法核实工作尾段，保留 uncertain 预算并受阻，不能为恢复而补零。

所需回归：在 quota 状态写入后、释放通知之前模拟重启，候选与评审各跑一次；cleanup 只针对原精确代次，释放证明补齐后不新建模型执行；清理失败按 REC-02 处理。重复 recover 不得重计预算或改写已结算片段。

### REC-06：轮换的所有终止入口尚未统一

当前显式移到队尾、清 visit_completed、in_pool=0 的代码只在 `_apply_result()` 的 failed/exhausted 或通过数达到阈值分支。`_settle_execution()` 的超时预算耗尽、`_block_evaluation()` 的评审受阻、`_close_finished()` 的场景完成均不走此分支。

这意味着访问可以在连续多项超时／评测受阻后仍留在池首；一个场景收口后也会继续本项目下一场景，不能完整表达设计第 6 节声明的“任务失败／耗尽或场景收口也可结束访问并轮换”。独立任务最终仍可执行，但轮换原因和池公平性不一致。

最小建议：持久化一个幂等的“本次访问结束”动作，覆盖计划／场景完成与各类最终局部收口；是否立即轮换以既定设计为准，不扩大为新的产品选择。不能在同一项目仍有候选写入时让新访问并发改写目录。

## Files Found

- `orchestrator/project_scenarios.py`：新场景任务、投递消费、执行／source、预算、候选／评审结果、逻辑计划及恢复。
- `orchestrator/project_iteration.py`：原项目门面、父状态／身份门禁、批次强阻断与恢复调度。
- `orchestrator/main.py`：QuotaGuard 原 Run 额度恢复、Scheduler 精确代次 finally 释放回调。
- `orchestrator/test_project_scenarios.py`：已有真实 SQLite、driver 提交及候选→评审测试；可扩展上述反例，不能以正常 happy path 替代崩溃窗口。
- `orchestrator/test_project_scenario_content.py`：合法分支激活、稳定 ID 和依赖测试夹具。
- `.trellis/tasks/10-21-project-scenario-workflows/prd.md`、`design.md`、`implement.md`：本次任务需求、冻结设计与执行验收边界。

## Code Patterns

- `ProjectIterationManager.execution_allowed()` 是原 Scheduler／QuotaGuard 共同父门禁，不能另建模型恢复旁路。
- `ProjectScenarios.execution_released()` 的事实粒度是精确 Run＋quota source，不能拿前一代证明替代当前代。
- 接受事务必须复核父 generation、task 当前状态与最新 job；本次不建议绕过 `_apply_result()`。
- 业务尝试由真实 user 消费认领，评审逻辑尝试同样由实际评审输入消费认领；排队和准备失败均不算一次模型业务失败。

## External References

无。本次问题由本地现有定义与控制流得出，不涉及外部接口或版本推断。

## Related Specs

- `.trellis/spec/vibecoding-bench/backend/project-iterations.md`：严格释放失败阻断批次、额度原 Run 恢复、正常计划 2+2+1、局部故障与历史终态保持。
- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md:531`：同身份、同 source 额度恢复；严格清理失败不得恢复；等待不持执行资源。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：私有执行租约、定向清理与实际退出证明。
- 当前 task `design.md:129`、`design.md:140`：只续验收、业务尝试和基础设施恢复、三层评审预算。

## Caveats / Not Found

- 本次为研究角色，按研究隔离规则未加载 implement.jsonl/check.jsonl；已读取任务三件套、相关规范与真实函数定义。
- 没有修改产品代码、规范或 Git 状态，没有启动真实模型／账号操作。
- REC-04 的旧路径和 REC-05 的当前恢复门禁有实际方法调用输出；其余结论以逐函数调用图为依据，未伪称真实 Docker 故障注入已通过。
- 主会话持续写入同一产品文件，最终检查应重新定位行号，并以修复后的针对性测试及真实容量 1／2 链路判定完成。
