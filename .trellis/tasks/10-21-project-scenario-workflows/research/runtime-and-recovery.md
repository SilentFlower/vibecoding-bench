# Research: 多场景任务的执行状态、预算与恢复

- Query: 核对现有项目计划的实际状态、SQLite 字段、原生会话证据、超时／额度恢复，分析多类型任务、依赖及条件材料接入所需边界。
- Scope: internal；只读源码与规范，仅写本研究文件，不决定问答采用人工还是模型评审，不给出最终数据库 schema。
- Date: 2026-10-21

## Findings

### 1. 核心结论

现有 schema 2 的「固定会话＋持久目录＋逐段证据＋独立验收＋严格释放」可以继续作为执行底座，但目前并没有独立的会话任务状态：通过一个步骤会同时推进线性下标、接受代码检查点并累计轮换步数。不能仅新增任务类型，再让问答沿用这段接受事务。

当前超时能保留已通过步骤、会话和半成品，以新 Run 接续原计划；真实 `quota_wait` 则复用原 Run 和步骤尝试，只增加额度执行代次。尚缺跨 Run 的累计有效工作时间、任务级条件材料状态、候选完成后只续验收、同项目内依赖局部阻塞，以及执行基础设施错误与业务尝试的完整隔离。

以下将现有事实和候选设计分开。文中的新概念是设计输入，均不是已存在的字段、表或 API。

### 2. 找到的文件

| 文件 | 作用 |
| --- | --- |
| `orchestrator/project_iteration.py` | 基础项目表、冻结发布、实例工作目录、旧单步调度、候选快照、原生 token 区间统计。 |
| `orchestrator/project_plans.py` | schema 2 计划表及升级、同会话多步、步骤验收事务、Run 接续、局部项目阻塞。 |
| `images/account/project_plan.py` | driver 侧候选通知、输入投递意图／确认、决定读取与阶段握手。 |
| `images/worker/entrypoint.sh` | 真实 CLI 启动、工作超时、原生最终回复判定、计划交接与管理等待时间补偿。 |
| `images/worker/task_followups.py` | 主会话消息读取、父链排序、既有固定业务补充；不是任意条件场景执行器。 |
| `orchestrator/account_runtime.py` | 实际目录、控制文件、执行来源和计划配置注入；共享 CLI 作业与定向控制。 |
| `images/account/cli-control.py` | 监督器、内核进程身份、完整作业树冻结／恢复与严格清理证明。 |
| `orchestrator/main.py` | `tasks/runs`、幂等初始化、Scheduler、QuotaGuard、启动恢复顺序、API 用量聚合。 |
| `orchestrator/project_library.py` | schema 1 内容、最小数量、线性依赖和 `app.py` 协议校验。 |
| `orchestrator/project_verifier.py` | 当前 JSON 行业务验收及业务超时／验证基础设施错误分类。 |
| `orchestrator/test_project_plans.py` | 同 Run、多次尝试、超时接续、投递不确定、迁移及停止竞争回归。 |
| `orchestrator/test_project_iterations.py` | 旧模式、快照／目录、验证基础设施错误、重启及用量边界回归。 |
| `orchestrator/test_quota.py`、`test_quota_completion.py`、`test_run_window_scheduling.py` | 额度／时段等待、身份、启动后复查、旧 Run 恢复及原终态保持。 |

### 3. 实际持久化结构与边界

项目基础表定义位于 `orchestrator/project_iteration.py:22`，计划表位于 `orchestrator/project_plans.py:22`；`main.init_db()` 先执行基础 schema、项目 schema，再调用 `initialize_plan_schema(conn)`，见 `orchestrator/main.py:1490`。

| 实际表 | 本次有关的现有字段与约束 |
| --- | --- |
| `project_catalog_releases` | `id,version,digest UNIQUE,relative_path,created_at`；冻结发布版本。 |
| `project_iteration_batches` | `account_id,account_identity,catalog_release_id,policy_json,status,generation,active_instance_id,stop_requested_at,next_launch_at,error`；升级另有 `launches_started,last_launch_at,wait_reason`。 |
| `project_instances` | `project_key,manifest_json,seed_digest,roadmap_digest,status,next_step_index,workspace_relative,started_at,checkpoint_digest,visit_order`；升级另有 `initial_order,in_pool,visit_completed`；`UNIQUE(batch_id,project_key)`。一个实例当前只有一个持续可写目录和一个已接受检查点。 |
| `project_step_attempts` | `instance_id,step_id,attempt_no,generation,run_id,expected_checkpoint_digest,validation_status,verification_errors,result_digest,report_relative,candidate_digest,accepted_checkpoint_digest,created_at,ended_at`；执行释放字段为 `execution_released_at,released_quota_attempt,execution_error`；升级另有 `plan_id,phase_seq,expected_prompt,native_start_json,native_end_json,fenced_at,fenced_source`。 |
| `project_execution_plans` | `instance_id,generation,start_index,target_index,completed_steps,session_id,execution_json,status,error,created_at,updated_at,ended_at`；开放状态 `ready/running/finalizing/quota_wait` 每实例至多一个。 |
| `project_plan_executions` | `plan_id,run_id UNIQUE,quota_attempt,source,phase_seq,current_attempt_id,request_relative,decision_relative,native_relative,cwd,evidence_start_json,decision_json,not_before,released_at,released_quota_attempt,execution_error,created_at,ended_at`；每计划至多一个 `ended_at IS NULL` 的执行。 |

`project_step_attempts` 基础旧定义中 `run_id UNIQUE`，但 `initialize_plan_schema(connection) -> None` 在识别已知旧结构后事务重建该表，解除这个唯一约束；复制全部旧列、主键、显式索引、自增序列，再幂等补列。当前仍保留 `UNIQUE(instance_id,step_id,attempt_no)` 和 `validation_status='passed'` 的实例＋步骤部分唯一索引。不能按基础建表字符串误判为「每步骤必须单独 Run」。见 `orchestrator/project_plans.py:51`。

通用 `tasks` 和 `runs` 另有历史语义，见 `orchestrator/main.py:1362`、`:1417`：

- `tasks` 的 `topic_no,title,prompt,account_id,timeout_sec,repeat_n` 用于原执行入口；项目计划也创建兼容任务，不能把它直接解释成新业务任务实体。
- `runs` 已有 `status,run_kind,workspace_dir,flows_dir,started_at,ended_at,stop_requested_at,error`，以及 `claude_code_version,claude_effort_level,execution_model,quota_attempt,quota_resume_at,window_wait_until,quota_identity`。
- 上述表**没有**任务累计有效工作秒数、场景状态、条件分支结果、分类型验收状态、独立 token 分项账本。
- `started_at` 在额度新代次排队时被清空，启动时重新写；不能用最后一对 `runs.started_at/ended_at` 推算整个任务跨代次成本。见 `orchestrator/main.py:3707`、`:6886`。

### 4. 可复用的实际方法与执行证明

| 实际签名 | 能复用的职责／限制 |
| --- | --- |
| `ProjectIterationManager.run_context(run_id: str) -> dict \| None` | 优先解析计划，兼容旧单步尝试；普通 Run 返回 None，见 `project_iteration.py:266`。 |
| `execution_allowed(run_id: str, *, started: bool = False) -> bool` | 重读父批次状态、generation、计划状态和 `not_before`，见 `project_iteration.py:280`。 |
| `prepare_workspace(row: dict, run_id: str, environment_root: Path) -> tuple[str,Path] \| None` | 实际启动时首次物化；后续只复用已发布目录，缺失／归属冲突拒绝，不重置 seed，见 `project_iteration.py:294`。 |
| `ProjectPlans.execution_configuration(run_id: str, source: str, quota_attempt: int, native_directory: Path, request_path: Path, decision_path: Path, cwd: str) -> dict \| None` | 启动前固定 cwd、来源、session、当前提示和字节起点；恢复核对检查点对象、会话存在、长度和原生可解析对话，见 `project_plans.py:277`。 |
| `ProjectPlans.execution_released(run_id: str, quota_attempt: int, error: str \| None) -> None` | 只按相同额度代次保存严格释放；已通过步骤的 `native_end_json` 不被最终 Run 释放覆盖，见 `project_plans.py:362`。 |
| `ProjectPlans._evidence(execution: dict, attempt: dict, plan: dict, request: dict) -> dict` | 核对阶段归属、实际 user 消费、最终 assistant、父链及回复后无新活动，见 `project_plans.py:528`。 |
| `ProjectPlans._can_resume_input(execution: dict, attempt: dict, plan: dict) -> bool` | 消费证据成立，或接受后尚未准备下一步有明确旧阶段状态时才允许接续，见 `project_plans.py:685`。 |
| `images/account/project_plan.py::process(action: str, config: dict, wait_seconds: float = 90) -> dict` | `begin/advance/sent`；返回 `waiting/send/complete/failed` 和 `held_sec`；有界等待决定，见 `project_plan.py:56`。 |

实际账号启动在 `orchestrator/account_runtime.py:1400` 调用计划配置，注入 `PROJECT_PLAN_JSON,PROJECT_SESSION_ID,TASK_PROMPT`，恢复时设置 `RESUME_SESSION_ID`。CLI 使用 `--resume` 或 `--session-id`，见 `images/worker/entrypoint.sh:1722`。

输入交接已有两层持久证据：driver 将下一指令状态先记 `delivery='sending'`，shell 真正注入后记 `sent`；确认丢失时以主 JSONL 已消费的 user 为准，不重复注入。缺少消费且发送结果不确定则报错，见 `images/account/project_plan.py:93`、`:129`。这可扩展至材料补充，但不能把原「下一步骤」字段直接当成任意条件分支。

候选安全性依赖完整作业树定向冻结。`_project_execution_control(run_id, quota_attempt, operation)` 只接受唯一匹配 source 的在途作业，见 `orchestrator/main.py:7794`；`images/account/cli-control.py:100` 的稳定内核暂停证明比「CLI 看起来空闲」更强。新任务验收仍需保留这些归属与竞争保护。

### 5. 必须解除的线性路线假设

| 当前假设与代码 | 多场景改造所需变化 |
| --- | --- |
| `ProjectLibrary._validate()` 要求 `step.requires == previous[-1:]`，见 `project_library.py:261`。 | 内容校验需允许稳定任务 ID 的真正依赖，验证引用存在、无环及条件可达性；不能强造前一步依赖。 |
| `_attempt()` 仅从 `manifest['steps'][next_step_index]` 取任务，见 `project_plans.py:422`。 | 候选任务必须由其自身状态、输入版本和依赖满足情况确定，顺序下标只能作为显示顺序。 |
| `reserve()` 用 `start_index/target_index` 表示连续范围，要求 `next_step_index == start_index + completed_steps`，见 `project_plans.py:472`。 | 冻结本轮明确的任务集合／顺序与分支规则；已完成集合不能仅从一个前缀推导。 |
| `_verify()` 回归 `steps[:index+1]` 的全部 checks，见 `project_plans.py:593`。 | 修改任务回归实际接受的代码能力及声明依赖；只读问答不能被当作新增程序检查，未选择分支不能列为必跑回归。 |
| `_accept()` 通过后同时改 `next_step_index/checkpoint_digest/visit_completed/completed_steps`，见 `project_plans.py:649`。 | 分开写任务结果与代码接受；只读任务可通过但保持原代码基线，任务数和接受代码次数分别统计。 |
| `_settle()` 以「通过步数等于连续范围长度」判断计划完成，见 `project_plans.py:724`。 | 一轮结束应按应执行任务及分支都有明确结果；整轮结束并不等于任务全通过。 |
| 修复用尽／验收环境错误把整个实例置 `blocked`，调度跳过该项目，见 `project_plans.py:655`、`:831`。 | 分开任务阻塞与项目／账号执行受阻；局部任务失败只阻塞其真正依赖后继，同项目的独立场景仍可调度。 |
| 每项目实例一个持续可写目录且每实例一个开放计划。 | 同项目的独立场景必须绑定固定基线并隔离现场；不能把失败任务的半成品交给独立任务。是否采用场景级工作区或其他显式隔离单位需在设计确定。 |

当前项目只因另一个项目阻塞而继续，并不具备同项目内按依赖跳过的能力。`test_failed_repairs_only_block_one_project` 与 `test_local_block_keeps_cause_and_allows_next_project_after_release` 只证明跨项目局部故障隔离，不能外推为任务图调度已存在。

### 6. 任务结果、代码接受、场景与 Run 的候选分离

这是满足 PRD 的候选职责划分，不是最终状态枚举或数据库定义：

1. **业务任务**：稳定 ID、类型、冻结输入、依赖及验收结果。完成的事实需要独立验收，正常最终回复只表示已有候选。
2. **对话阶段**：首问、已经披露的材料、当前分支、正在等待的回答；澄清和材料投递不增加任务覆盖数。
3. **业务尝试**：首轮或有限继续／修正；一个尝试可以因额度或基础设施重新拉起多段实际执行。
4. **实际执行**：沿用 Run、source、quota_attempt、租约和严格释放证据；Run 终态属于进程执行事实，不能覆盖业务验收事实。
5. **代码版本**：冻结任务输入版本、未通过候选、已接受检查点分别保留。只读任务记录所读版本及回答，不自动发布当前目录成为已接受代码；修改任务通过才产生明确代码接受。
6. **场景与整轮**：选定分支的必要任务均达到明确状态后才能收口。独立任务继续，依赖失败的任务标明阻塞原因；通过数、失败数、未完成数与运行结束分别展示。

当前 `_capture(instance)` 已把现场封存为内容寻址快照，见 `project_iteration.py:780`；可以继续保存失败半成品及不可变候选。只读任务仍需定义允许的临时文件范围并核对代码输入未被意外修改，不能因为无意改动而把这些文件自动接受为代码检查点。

独立场景还需隔离会话上下文。仅重建基线文件、仍复用包含另一场景答案或未接受修改的主 session，不足以保证输入固定；同一业务场景内的接续则应保留原 session。现有「同计划同 session，新计划新 session」可以作为兼容底座，但场景映射需新契约。

### 7. 条件材料与依赖调度候选

`images/worker/task_followups.py::process(action, state_path, project, run_id, initial, followups, resume=False, idle_seconds=10, allow_next=True, timing=None)` 当前支持冻结的零至两条补充，并按既定阶段／时间推进，见 `task_followups.py:329`。没有按诊断需要选择材料、按结论选择分支或任意任务依赖图。

可复用主 JSONL 解析器 `read_dialogue(path: Path, offset: int = 0, include_queue: bool = False) -> list[dict]`：排除 sidechain/meta/synthetic，保留消费、父链及字节证据，见 `task_followups.py:168`。不能仅凭队列入队／发送成功推断模型已经处理材料。

候选执行规则：

- 场景定义首问、允许披露的材料、可选条件分支与结束条件；运行开始冻结内容与版本，参考答案／验收材料留在控制端。
- 收到澄清请求时记录它属于哪个任务和哪一输入阶段；根据冻结材料规则决定披露内容，先落投递意图再发送，并按实际消费确认。选择规则是自动还是人工，留给主会话产品决定。
- 若材料由外部用户补充，需持久化「待材料」而不一直占用 CLI／冻结作业树；现有 driver 只有默认 90 秒管理等待，不适合直接等待长时间人工操作。
- 等待材料不是新任务；原任务是否以「合理澄清」作为合格最终结果，必须由该任务预设结束条件决定，不能让模型任意询问信息就算通过。
- 调度按依赖满足且输入版本可用选任务。代码依赖必须绑定已接受版本；知识依赖也需明确所需结果，不能只看某个步骤下标。
- 依赖失败只传播到真正后继；未选中的互斥分支记录为不适用，不能算失败，也不能加完成覆盖数。
- 账号认证失效、身份变化、执行树无法严格清理等共享风险继续阻断对应执行范围；不能为了继续独立任务绕过账号公共门禁。

### 8. 超时、只续验收及重启：实际路径与缺口

#### 8.1 现有超时接续事实

`ProjectPlans._inspect()` 遇 Run 终态先调用 `_settle()`，见 `project_plans.py:773`。严格释放且输入可确认后，尚未验收的当前尝试会经 `_finish_failure()` 保存半成品、结束该尝试；原计划保留 `completed_steps` 并回 `ready`，下一 `reserve()` 创建新 Run、新尝试，保留计划 session 和剩余范围，见 `project_plans.py:729`、`:756`、`:466`。

已通过任务不会因这个恢复从头重做，因为实例下标和计划 `completed_steps` 已在接受事务中持久化；`execution_configuration()` 会核对接受检查点、会话缺失／截断、真实对话，见 `project_plans.py:303`。缺证据时只保留现场并阻塞，不换新 session 或重建 seed。

但新 Run 的提示仍是 `_prompt()` 生成的原工程步骤加失败证据，见 `project_plans.py:397`；当前没有通用「恢复类型」区分继续回答、继续修改、只继续验收。

#### 8.2 完整候选只续验收尚未实现

`_verify()` 仅在 `run_status='running'` 的 `_inspect()` 分支触发，且需要活跃执行的 freeze 证明。Run 已结束后 `_settle()` 对未结束尝试直接记录失败；不会先用此前候选通知恢复独立验收，见 `project_plans.py:773`、`:729`。

目前 `snapshot` 在验收前写入对象库，但 `candidate_digest`／结果／决定的主要数据库接受操作在 `_accept()`；若验收中断，尚缺独立的「已冻结候选、待验收」持久事实及可重入验收作业。不能以「对象库中存在某个快照」推断它属于当前任务的最终候选。

候选补法：在停止模型工作或发起验收前，持久化候选与任务／尝试／输入版本／最终消息／字节边界的绑定；严格释放后，如候选证明完整，仅恢复该候选的验收，既不重发用户问题也不消耗模型修正次数。若没有完整候选，再按实际消费证明恢复模型执行；证明冲突则受阻。接受事务仍需 CAS、generation 和唯一接受约束，迟到验收不得覆盖新结果。

#### 8.3 重启事实及必须保持的顺序

- `ProjectPlans.recover(cleanup)` 跳过真正 `quota_wait` 和明确从未启动的 queued；其余开放执行先严格清理，非终态写失败并保留计划／现场，见 `project_plans.py:380`。
- 管理器旧模式 `recover(cleanup)` 同样先收口，见 `project_iteration.py:556`。
- lifespan 先 `quota_guard.recover()`，再 `project_iterations.recover(runner.cleanup_quota_run)`，随后启动后台调度，见 `orchestrator/main.py:7856`。新恢复不能让旧执行和新执行并行。
- 已接受的 `decision_json` 可以重发，阶段不匹配的旧通知不会再次验收，见 `project_plans.py:574`、`:507`。
- 需要新增任务／预算／候选恢复对账，但保持原停止意图、账号身份及额度代次保护；不可单靠内存队列或 process-local timer 恢复业务状态。

### 9. 首轮＋两次继续／修正与基础设施分类

当前 `_attempt()` 取该实例＋步骤最大 `attempt_no + 1`，超过 3 拒绝，见 `project_plans.py:426`；普通验收失败在同 Run 内新建尝试，超时后新 Run 也新建尝试。`repair_limit` 默认是 2，但 schema 2 `_attempt()` 的 3 是现有硬限制，不能宣称公开 API 可配置该次数。

真实 `quota_wait` 不关闭当前尝试，计划和实例仅进入等待。恢复由 `QuotaGuard._resume_account(account)` 沿原 Run＋task＋模型快照创建新额度代次，见 `orchestrator/main.py:3652`；计划不新增尝试，见 `project_plans.py:779`。

验证容器错误已经单独处理：`verifier_report(candidate, cases)` 最多本地验证两次；两次 `error` 后阻塞，不生成模型修正，见 `project_plans.py:610`。旧模式使用 `verification_errors` 计数，见 `project_iteration.py:817`。程序超时是业务失败，Docker 等异常是 `error`，见 `project_verifier.py:95`、`:124`。

然而以下执行层基础设施错误仍会变成 Run `failed`：凭据同步的临时异常、非 `RuntimeBusy` 的启动异常、等待／读取异常，见 `orchestrator/main.py:6863`、`:6913`、`:6992`。`_settle()` 没有针对这些错误完整区分业务失败，可能结束当前尝试、下一次 reserve 再增 `attempt_no`；实际 `_attempt()` 又发生在真正投递之前。因此「所有基础设施故障都不消耗业务尝试」尚未满足。

候选计数边界：

| 事件 | 业务尝试与成本处理方向 |
| --- | --- |
| 首次解决任务的输入实际被消费 | 认领首轮业务尝试，不能仅因为创建队列行就扣次数。 |
| 明确业务失败后要求修正，或工作超时后要求继续 | 同一任务新增有限尝试，合计最多 3；已耗时间与 token 保留。 |
| 正常条件材料／必要澄清 | 同任务的对话阶段，不增加覆盖数；其成本属于原任务，并需明确阶段上限以避免无限问答。 |
| 真正额度耗尽、窗口等待、共享容量等待 | 不增加业务尝试；等待不计有效模型工作时间，已有工作成本仍保留。 |
| 启动／基础设施故障，尚未投递业务输入 | 原业务尝试不扣；执行故障另记并有界恢复，不能无限自动重启。 |
| 中途基础设施故障，已产生部分模型工作 | 不因基础设施恢复额外扣业务修正次数；已产生的工作时间／token 不能抹掉，输入不确定时受阻。 |
| 完整候选已有，仅重试独立验收 | 不增加模型业务尝试；验收重试有独立上限与耗时／费用记录。 |

上表是针对 PRD 的候选实现契约，不代表旧 schema 1／2 应被追溯改写。应区分任务结论、执行原因、可否恢复，而不是从一段 error 字符串直接扣次数。

### 10. 跨 Run 的累计有效运行时间

当前真实 driver 在初始提示注入后记录 `run_started_at`，设置 `deadline = now + TIMEOUT_SEC`，见 `images/worker/entrypoint.sh:1761`、`:1779`。同 Run 里每步骤通过或修复不重置这个 deadline；`v3-project-plan advance` 的管理等待通过延后 deadline 排除，见 `entrypoint.sh:1923`。

现有能力只覆盖**本次 driver**。`reserve()` 新 Run 的任务仍直接取批次 `policy['timeout_sec']`，见 `project_plans.py:485`、`:502`；额度恢复也从原 task 传完整 `timeout_sec`，见 `orchestrator/main.py:3719`。没有把前段已用有效秒数扣掉的持久化逻辑。`held_sec` 是返回值，并没有写成跨执行累计账本。

`cli-control.py::supervise(...)` 的持久退出结果含身份、`cleaned`、`exit_code`，没有工作阶段累计时间，见 `images/account/cli-control.py:212`、`:247`。其中内核 `started` 是 PID 身份用 tick，不是业务开始时间或预算余额。

候选要求：

- 为同一任务维护跨业务尝试和实际执行片段的累计有效时间；每段关联任务、尝试、Run/source／代次，关闭与聚合要幂等。
- 工作时间应覆盖模型思考、工具执行和实际解决过程；排队、环境准备、额度／时段等待、待材料、人工审核与独立验收另记，不能全部用墙钟差当模型工作时间。
- 片段内使用单调时钟，恢复时使用已持久化累计值；新 Run 可用预算取任务剩余，不能重新获得整份预算。每次材料交接或验收时停止／切换工作计时。
- 需要定义周期性持久化、来源／进程身份和最后活动证明，覆盖控制端崩溃、driver 退出但汇报未到等窗口。主机重启后不能把另一 boot 的 monotonic 值直接相减。
- 最后片段尾部无法精确确认时必须显式保留不确定性及保守恢复策略；不能默认为零从而凭重启无限续时。具体是保留上界还是要求对账需在设计确定。
- 达到累计预算上限或三次业务尝试上限，任务以未完成／预算耗尽明确收口；其真正依赖后继受阻，独立场景继续。执行安全或输入证明不可靠仍优先受阻。
- 「整个 Run 的保护超时」与「单个任务累计业务预算」应分别定义，避免同 Run 多任务共享一份 timeout 后误称每任务都有同额预算；原 schema 2 的整计划 timeout 保持旧含义。

### 11. token 成本与未知状态

`ProjectIterationManager.native_usage(run_id, directory, input_counter, *, boundaries=None)` 已按本次字节边界读取主 assistant usage，排除 sidechain/meta，以消息 ID／request ID 去重；同响应保留输出计数较大的样本。缺边界、截断、越界或扫描不完整返回 `usage_available=False`，见 `project_iteration.py:455`。

`step_usage(attempt_id, input_counter)` 使用该尝试 `native_start_json/native_end_json`，不复制整个共享 Run，见 `project_iteration.py:513`。额度恢复前封存未完成尝试终点，新代启动保留原尝试起点并清当前终点，因此当前尝试可覆盖额度多段；结束的历史步骤终点不被覆盖，见 `project_plans.py:346`、`:376`。

公开 `GET /api/project-instances/{iid}/usage` 按 `step_id` 聚合全部尝试，返回 `attempts,known_attempts,complete`。全无统计时 tokens 为 null；部分已知时给已知和，但 `complete=false`，见 `orchestrator/main.py:10248`。这个 `complete` 仅表示统计记录可用性，不是任务完成或预算结束。

现有 `_usage_input_tokens(usage)` 把普通输入、cache creation、cache read 合并为 `tokens_in`，见 `orchestrator/main.py:323`。当前项目用量没有分别公开缓存分项，也没有保存独立评审成本。

候选成本契约：

- 延续原生消息去重与区间，不按任务数量乘整 Run 总量；任务全部尝试、澄清与材料的成本一起累计。
- 扩展任务类型、输入／输出／缓存分项与模型执行／验收执行归属；不能用合并 `tokens_in` 精确推导现金价格。
- 使用量未知、部分已知、已可靠封存分别表达；日志存在一个 usage 不代表整次成本完整，当前 `usage_available` 比严格完整性弱。
- 恢复不能因为看到 `usage_available=False` 把它补为 0；若将来 token 预算作为硬上限，未知 token 也不能被当作剩余预算无限继续。PRD 当前明确的是累计时间预算，不必擅自引入 token 硬阈值。
- 主会话聚合会排除 sidechain，沿用时应明确统计范围；不能将其宣称为所有子代理或外部调用的完整账单。
- 如果未来选择独立模型评审，评审费用单列，并通过批准的统一执行／记账路径实现；本研究未发现该能力已由上述项目执行器提供，也未替用户选择评审方式。

### 12. 旧 schema 1／2 的保留与迁移约束

这里有三种互不等价的 schema 概念：内容 catalog／project 的 schema 1、无 `policy.schema` 的旧单步批次，以及 `policy.schema=2` 的同会话计划批次。不能把它们统称一个版本或升级时覆盖解释。

- 旧批次默认策略为 `DEFAULT_POLICY`，`create_batch(..., policy=None)` 保留旧单步语义；传策略字典经 `normalized_policy()` 固定为 schema 2。分流在 `project_iteration.py:615`，新 API 总传策略字典，见 `orchestrator/main.py:10194`。
- 当前旧发布通过 `catalog_release_id` 与冻结 manifest 引用；`_release(release_id)` 重新读取固定发布并核对摘要，见 `project_iteration.py:383`。旧实例目录、半成品、失败快照与已接受版本不因新内容接入而重建。
- 候选路线一：为新混合场景显式增加内容／执行版本，保留旧 reader 与旧调度器；共享基础运行、额度和清理设施。候选路线二：增加通用任务状态实体，在新版本使用，旧数据保持原结构或仅建立非破坏映射。最终选择由设计收敛，不能在研究中先定字段。
- 新语义不能直接复用 `next_step_index` 作为任务完成数，不能把旧 passed 自动解释成新问答验收通过，不能把旧未知用量补零或补造历史工作时长。
- 历史 API／页面可显示旧「工程步骤」及原计划范围，新内容显示场景／任务／代码接受；旧 `completed` 的含义保持可解释。新整轮结束允许含失败时不能反向修改旧 completed 定义。
- 数据库新增结构应幂等、事务、有旧数据库回归，并保留 ID、引用、索引与自增序列；原迁移已有明确实现和测试可复用。未知旧结构必须拒绝猜测重建。
- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md` 早期 Migrations 段落仍含 P1 删除 DB 重建说明；本任务 R10、后续项目／额度持久化契约明确要求保留历史，因此**不能采用删库重建**。
- 回滚前需识别新旧执行版本与在途状态，不允许旧调度器解释新状态后盲发；旧 schema 1／2 不需要靠恢复退役生成内容兜底。当前正式 catalog 为空，新内容就绪前项目入口仍可能 503，普通题库继续保持可用。

### 13. 验证落点与现有测试证据

以下仅是已读取的测试及后续可运行命令，本轮未运行测试、Docker 基线、模型调用或付费实验。

| 已有测试 | 实际覆盖 |
| --- | --- |
| `ProjectPlanTests.test_same_run_two_steps_and_usage_boundaries` | 单 Run／session 两步、检查点与 token 不重复。 |
| `test_timeout_one_of_two_preserves_partial_and_resume_range` | 1／2 后超时保留旧 Run、半成品、session，新 Run 只补剩余一步。 |
| `test_real_quota_wait_keeps_run_step_attempt_and_native_session` | 同 Run、同 attempt、同 session 的额度新代次。 |
| `test_missing_resume_session_blocks_and_keeps_partial`、`test_missing_checkpoint_blocks_without_rebuilding_seed` | 缺失证明不重建现场。 |
| `test_truncated_original_session_cannot_reset_byte_evidence`、`test_quota_partial_dialogue_cannot_be_truncated_to_last_checkpoint` | 会话截断不重置字节证据。 |
| `test_consumed_input_recovers_lost_send_ack_without_resending`、`test_uncertain_input_without_native_consumption_blocks_recovery`、`test_accepted_checkpoint_before_next_send_resumes_remaining_step` | 输入消费与发送确认丢失、禁止盲发。 |
| `test_failed_repairs_only_block_one_project`、`test_local_block_keeps_cause_and_allows_next_project_after_release` | 三次业务尝试、跨项目局部阻塞。 |
| `ProjectPlanMigrationTests.test_old_attempt_ids_indexes_sequence_and_repeat_upgrade` | 旧主键、索引、自增序列与重复升级。 |
| `test_project_iterations.py::test_verifier_infrastructure_errors_never_trigger_model_repairs` | 验证基础设施错误本地重试，不生成模型修复。 |
| `test_restart_retains_workspace_and_pending_step` | 旧管理器重建保留工作目录和排队步骤。 |
| `test_quota.py` 的 `test_restart_cleans_old_worker_before_restoring_wait`、`test_runtime_quota_wins_exit_zero_and_keeps_same_run`、`test_first_wait_freezes_model_and_identity_change_cancels_old_work` | 额度优先、先清理、固定身份和模型。 |

后续基础回归命令可用 `cd orchestrator && python3 -m unittest test_project_plans test_project_iterations test_quota test_quota_completion test_run_window_scheduling`；具体依赖使用项目既有测试环境。本研究不以未执行命令宣称通过。

新增验证至少覆盖：

1. 三个问答任务通过而代码接受计数／摘要不变；错误回答不能因正常退出而通过。
2. 同项目独立任务继续、失败依赖后继受阻、未选择分支不进失败／通过分母；各自固定输入版本。
3. 条件材料恰好一次投递、确认丢失不重复、合法澄清不加覆盖数、长期待材料不占 CLI。
4. 候选完成后验收中断／服务重启，仅重验该候选，不重新调用模型、不新增业务尝试。
5. 时间预算跨 Run／quota 代次／业务尝试累计且幂等；排队、待材料、额度等待、验收不计工作秒；崩溃尾段未知不清零。
6. 三次业务尝试上限；启动前失败不扣、已产生部分工作不抹成本、验证错误仅重验；无界基础设施重试被单独限制。
7. token 全未知／部分已知／消息重复／缓存分项／恢复多段不重计，统计完整性与任务状态互不混淆。
8. 旧 schema 1／2 已有批次、开放计划、历史成果、未知统计和普通题库读取语义保留。

真实 driver／Docker 需复用规范中 `deploy/v3/run_local_verification.py --manifest <联合清单> --project-scheduling-only` 的隔离合成场景，新增只续验收和跨恢复预算断言；它证明运行机制，不能当作真实模型效果。真实 UI/API/SQLite 联测沿 `verify_stack.py --manifest <联合清单> --browser --project-iteration` 扩展。外部模型评审若获选择，另按实际评审执行路径定义测试。

### 14. 相关规范与外部引用

- `.trellis/workflow.md`：研究角色只写本任务 research，规划未审阅前不能实施。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md`：冻结发布、schema 1／2、严格释放／定向冻结、有限修复、逐步骤用量、目录保留与旧内容退役。
- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md`：SQLite 写锁和幂等升级；被动额度原任务恢复；真实耗尽、百分比阈值与当地时段的不同语义。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：共享 CLI 容量、source／进程身份、执行级设置、定向清理和重启对账。
- `.trellis/tasks/10-21-project-scenario-workflows/prd.md`：R1～R10、AC1～AC8 与待决评审方式。
- 外部引用：本题只核对仓库已有实现，没有引入第三方库或新协议，因此未进行外部检索，也未对外部 CLI 新版本行为作推断。

## Caveats / Not Found

- 没有最终数据库 schema、实现代码、迁移脚本或产品决策；候选状态／职责划分不能被当作已经支持的新 API。
- 未执行测试、Docker 基线、真实 CLI、模型调用、发布或部署；已有测试名称是代码证据，不是本轮通过报告。
- 本次检查的主路径中未找到跨执行有效工作时间账本、候选待验收的持久独立作业、同项目任务依赖图及条件材料执行器。不能以「有恢复方法」概括为这些要求已全部具备。
- 当前会话恢复主要核对持久字节位置、内容可解析和接受检查点对象，并非每条历史 JSONL 都有独立不可变摘要证明；新候选绑定和恢复完整性应明确证据覆盖范围。
- 问答／方案的验收采用人工还是独立模型评审仍是主会话待决产品选择，本报告仅指出两者均需可持久化的待验收及恢复边界。
- 正式内容库为空和旧协议 `app.py` 约束仍是接入前提问题；不能只修调度器便声称三个真实项目已经可执行，更不能把 100 仓研究完成数换算成新任务模型完成数。
