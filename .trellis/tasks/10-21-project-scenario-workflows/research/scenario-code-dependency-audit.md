# Research: 显式代码依赖与半成品恢复定向审查

- Query: `_bind_code_dependencies()`、候选 `parent_code_digest`／父作业记录、多个代码依赖、目录交接中断以及同任务恢复是否精确绑定。
- Scope: internal，只读产品；实际探针使用内存 SQLite 和本研究目录中的临时文件，结束已清理。不执行 Check-All。
- Date: 2026-10-21

## Findings

本次发现并复现两项问题，主会话已在审查期间加入修复。最新代码的定向复核未留下新的未解决发现。下面保留反例、修复定位与实际探针输出，避免把发现时的旧行为误当成最终实现。

### CODE-01：用内容摘要合并父链，会把真实分叉误认为同一继承链

原实现的 `parents` 使用 candidate_digest 作键。不同接受作业可能产生相同字节，例如显式回退；后来的同字节作业会覆盖早期作业的父指针。

可复现的合法接受顺序：

1. U 接受状态 D0。
2. A 显式依赖 U，接受 D1。
3. B 显式依赖 U，接受 D2；A 与 B 是分叉。
4. C 显式依赖 A，将代码回退为与 U 相同的 D0。
5. 新任务同时声明 code 依赖 A、B。按接受作业 B 的真实继承链，A 不在链上，应受阻。

旧实现却构造出 `D2 -> D0 -> D1 -> D0`，因为 `parents[D0]` 被 C 覆盖。它因而以 B 的 D2 为 base 并发布 ready，实际 B 没有继承 A。

已用真实 `_bind_code_dependencies()` 与内存 SQLite 复现：

```json
{"siblings_A_B_accepted":true,"chosen_base":"D2","marker_state":"ready","dependency_jobs":{"2":"D1","3":"D2"}}
```

去掉后来的 C，完全相同的 A／B 依赖则正确受阻，证明误判来自同字节父链覆盖，而非测试输入本来存在继承关系。

主会话修复后，marker 增加 `base_checkpoint_job_id`，capture evidence 增加 `parent_code_job_id`；`parents` 沿真正接受 job.id 遍历，parent_code_digest 保留为内容取证，不再用它折叠作业身份。定位：`orchestrator/project_scenarios.py` 的 `_bind_code_dependencies()` 父链构造，以及 `capture_submission()` 的 evidence 保存。

修复后的同一探针实际输出：

```json
[
  {"requires":["A","B"],"status":"blocked","reason":"多个代码依赖没有同一已接受继承链，不能猜测合并"},
  {"requires":["U","B"],"status":"ready","base_job":3},
  {"requires":["A","C"],"status":"ready","base_job":4}
]
```

因此分叉被拒绝，真实继承链及真实回退链仍可使用。

### CODE-02：新独立任务会把前任务未接受的代码夹带进已接受检查点

原目录替换条件为 `if dependencies and snapshot_tree(workspace)['digest'] != base`。没有显式 code 依赖的新任务仍记录 scene.checkpoint_digest 为父状态，但直接继承当前工作目录。

具体反例：

1. 已接受状态 A 的 `library/example.py` 为 VALUE=1。
2. 前一个 modify 任务失败，目录留下 VALUE=2，尚未被接受。
3. 后一个独立 modify 任务只允许修改 app/，首次准备输入时却把 VALUE=2 的脏树封存为 prepared baseline。
4. 该任务只改 app/main.py；范围检查 prepared -> candidate 通过。
5. 若其自身原生业务／回归满足，接受的是包含 VALUE=2 的整棵候选树；前一任务的未接受库改动被一起接受，而 parent_code_job_id 仍指 A。

真实绑定函数与真实范围检查给出：

```json
{
  "new_task_requires":[],
  "bound_parent_is_accepted":true,
  "workspace_checked_or_replaced":false,
  "scope_against_prepared_dirty_input":"passed",
  "scope_against_declared_parent":{
    "status":"failed",
    "changed_files":["app/main.py","library/example.py"],
    "unauthorized_files":["library/example.py"],
    "feedback_codes":["unauthorized_change"]
  }
}
```

主会话已把“首次任务绑定时恢复确定父状态”扩展到没有 code 依赖的新任务。此改变不影响已有 ready marker 的同任务接续：marker 的早返回仍保留当前业务半成品。

同时核对了入口材料：若没有已接受代码作业，且场景入口材料已在候选启动前冻结，最新代码先验证 entry-inputs.json 的 scenario_id／entry_key，再使用其 input_checkpoint_digest 作为确定基线，避免恢复裸 seed 时丢掉合法入口文件。已有接受代码或显式 code 依赖使用其完整冻结候选，该候选本身已包含对应业务起点。

定位：`orchestrator/project_scenarios.py` 的 `_bind_code_dependencies()` 中 entry marker 归属检查、无条件脏树比较、目录替换；`orchestrator/test_project_scenarios.py` 中 `test_new_task_without_code_dependency_excludes_unaccepted_changes()`。

## 已实际核对的交接与恢复边界

以下没有发现新问题，不扩展为全链路通过结论：

- 显式依赖首先要求目标任务 passed、存在 accepted_checkpoint_digest，并能找到对应 passed evaluation job；缺证明不会拿当前目录替代。
- 内容快照通过真实 `snapshot_tree()`／对象库保存，目标检查点走原 `_checkpoint()` 的清单与对象摘要／大小核对。
- 交接先保存原树及 replacing marker，再执行两次 rename。第二次 rename 中断时工作区可暂缺，但旧目录和 staging 均保留；重试拒绝猜测。
- 已替换新目录、但 ready marker 发布前中断时，replacing marker 仍阻止重试；原目录留在 saved 路径。
- ready marker 已存在且依赖一致时，同任务后续调用不重新比较／替换工作树，半成品保持。

后三项实际使用真实快照、对象验证、物化与文件 rename，仅在本研究临时目录注入第二次 rename 或 ready 发布错误，结果为：

```json
[
  {"case":"second_rename","marker":"replacing","retry":"blocked","old_partial_preserved":true,"workspace_exists":false},
  {"case":"ready_marker","marker":"replacing","retry":"blocked","old_partial_preserved":true,"workspace_exists":true},
  {"case":"same_task_resume","marker":"ready","partial_preserved":true}
]
```

临时目录经 TemporaryDirectory 正常清理；未改候选真实目录、产品代码、规范或其他任务。

## Files Found

- `orchestrator/project_scenarios.py`：任务起点、显式代码依赖、父作业身份、交接 marker、候选 evidence 与机械范围基准。
- `orchestrator/project_library.py:98`：真实快照和内容对象；`project_library.py:148` 为从固定对象物化到新目录。
- `orchestrator/project_plans.py:247`：原检查点清单及逐对象大小／摘要／文件类型验证。
- `orchestrator/project_iteration.py:847`：候选捕获、对象记录及固定候选目录。
- `orchestrator/project_evaluation.py:18`：真实授权范围比较，须对确定输入基准使用。
- `orchestrator/project_scenario_content.py:159`：依赖同场景、无环、code 只引用 modify 的内容限制。
- `orchestrator/test_project_scenarios.py`：主会话已补显式依赖、分叉拒绝、同字节回退与新独立任务排除未接受改动反例。

## Code Patterns

- 内容相同不等于接受作业相同；多依赖继承判定沿 job 身份走，内容摘要用于核对字节。
- 首次任务输入绑定与同任务继续是不同动作；前者恢复确定基线，后者复用 marker 并保留半成品。
- 检查点接受是整树接受，授权检查的 before 不能混入前一失败任务的未接受改动。
- replacing marker 是保守停止证明；缺 ready 不从“目录看起来存在”推断交接完成。

## External References

无。全部结论来自本地现有定义和实际受控探针。

## Related Specs

- 当前任务 `design.md` 第 4 节：明确代码依赖、同一接受继承链、切换前封存与同任务恢复保留半成品。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md`：固定检查点、候选范围验收、可靠恢复与保留现场。
- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md`：持久归属与原事实不被恢复覆盖。

## Caveats / Not Found

- 这是定向研究，不是 Check-All；没有执行 Check-All 或接管 inline 实现。
- 两项发现均已在审查期间由主会话修复；本报告保留发现时输出和修后核对，不把旧行为继续列作未解决问题。
- 主会话报告其新增测试后 24 项通过；研究代理未重复执行这组已通过检查，也不将该口头结果充当自己的独立测试记录。
- 本报告的独立运行证据限内存 SQLite、真实方法及研究临时文件交接，未声明真实模型或 Docker 故障注入已完成。
