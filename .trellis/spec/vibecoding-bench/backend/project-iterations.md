# 项目迭代模式契约

内容 schema 3 的完整需求／BUG 周期复用 policy 3，见末节；历史内容 schema 1／2 继续遵守各自冻结版本。

## Scenario: legacy 内容 schema 1 的线性步骤与计划执行

本节的单步与同 CLI 多步分别指无 schema 的旧执行策略与 policy 2；其中历史“schema 2”均指执行策略版本，不是内容 schema 2。共享停止、鉴权及文件交接继续适用；新场景使用后节 policy 3 契约。

### 1. Scope / Trigger

- 修改 `orchestrator/project_{library,iteration,plans,verifier}.py`、`images/account/project_plan.py`、`run_kind='project_iteration'`、项目管理 API、`#projects` 页面或项目内容打包时适用。
- 项目调用 `orchestrator/main.py` 的共享停止入口、决定文件跨 UID 交接时也适用。
- 本模式依赖 v3 固定账号运行环境；普通题库、批次、养号、抓包和续聊继续使用原有身份及状态语义。
- 内容、路线和业务验收归本文件；Docker 账号角色、租约、认证及原额度恢复继续遵守 [account-runtime-v3.md](./account-runtime-v3.md) 与 [database-guidelines.md](./database-guidelines.md)。

### 2. Signatures

控制端入口：

```python
ProjectLibrary(root, minimum_projects=100, minimum_steps=20)
ProjectLibrary.install(data)
ProjectIterationManager.create_batch(account_id, name, project_keys=None, policy=None, scenario_entries=None)
ProjectIterationManager.transition(batch_id, action)
ProjectIterationManager.prepare_workspace(row, run_id, environment_root)
ProjectIterationManager.execution_released(run_id, quota_attempt, error=None)
initialize_plan_schema(connection)
ProjectPlans.execution_configuration(run_id, source, quota_attempt,
                                    native_directory, request_path, decision_path, cwd)
ProjectVerifier.verify(candidate, cases, timeout=30)
write_document(path, value, *, mode=0o600, owner=None) -> None
_stop_project_run(rid) -> dict
```

账号侧 `images/account/project_plan.py` 使用 `_read(path, maximum=65536) -> dict` 读取控制文件；仅原子替换引起的旧 fd 链接数归零允许有限重开。

API 均位于原 cookie 鉴权下：

| 方法／路径 | 输入或结果 |
| --- | --- |
| `GET /api/project-catalog` | `version,digest,projects`，项目摘要含 `project_key,seed_digest,step_count,milestones` |
| `GET /api/project-catalog/{key}` | 公开目标与依赖，不返回参考实现 |
| `POST /api/project-iteration-batches` | 原账号、名称和项目键，加严格整数策略字段；按内容版本创建 policy 2 或 policy 3，不接受调用方直接指定 schema |
| `GET /api/project-iteration-batches[/{id}]` | 批次的 `status,policy,counts,scheduling`；详情另含 `instances`，实例含 `in_pool` |
| `POST /api/project-iteration-batches/{id}/{start\|pause\|stop}` | 返回最新批次详情 |
| `GET /api/project-instances/{id}` | 路线、尝试和 `plans`；计划含固定范围、完成步数和关联 `runs`，执行状态、`validation_status` 分开 |
| `GET /api/project-instances/{id}/usage` | 按步骤聚合尝试，缺失证据为 null；`complete` 仅表示各尝试都有记录 |
| `GET /api/project-step-attempts/{id}/artifacts` | 固定报告、摘要、文件清单和可用的版本差异 |
| `GET /api/project-step-attempts/{id}/file?path=...` | 清单内文件的有界文本预览 |
| `GET /api/project-iterations-stream?batch_id=...&instance_id=...` | `project-state` SSE；实例必须属于所选批次 |

`name` 默认“项目迭代批次”，去除首尾空白后为 1～120 字符；项目选择不可空、重复、超出 100 项或不属于当前版本。省略项目键表示全选。

新策略字段拒绝 bool、字符串和小数，不静默夹取显式非法值：

| 字段 | 默认 | 范围与边界 |
| --- | --- | --- |
| `concurrency` | 2 | 1～2 且不超过账号与有效活动池；省略时按实际容量取默认 |
| `active_projects` | 3 | 1～100，有效值不超过所选项目数 |
| `rotation_steps` | 5 | 正整数，不超过所选路线最大步数，只计验收通过 |
| `steps_per_plan` | 2 | 同一 CLI 内的计划步数；正整数，不超过所选路线最大步数 |
| `timeout_sec` | 1800 | 60～86400，覆盖整个本次计划执行 |
| `interval_min_sec/interval_max_sec` | 0／0 | 0～86400，最大值不小于最小值；只作用于计划补位 |

`scheduling` 返回 `account_concurrency_limit,configured_concurrency,active_runs,running_count,wait_reasons,admission,next_launch_at`；公开计划不返回原生 session、PID 或进程证明。额度来自账号设置，不另存一套批次阈值。

SQLite 的 `PROJECT_SCHEMA` 由 `init_db()` 幂等执行，新增：

- `project_catalog_releases`：`digest UNIQUE`，固定发布路径。
- `project_iteration_batches`：账号、创建时身份、内容版本、`policy_json,generation,status,active_instance_id`。
- `project_instances`：`UNIQUE(batch_id,project_key)`，冻结 manifest、基线／路线摘要、`next_step_index,workspace_relative,started_at,checkpoint_digest,visit_order`；新增 `initial_order,in_pool,visit_completed`。
- `project_step_attempts`：保留 `UNIQUE(instance_id,step_id,attempt_no)`；保存代次、预期 checkpoint、执行释放证据、候选／报告／已接受摘要。迁移解除 `run_id UNIQUE`，增加 `plan_id,phase_seq,expected_prompt,native_start_json,native_end_json,fenced_at,fenced_source`；`validation_status='passed'` 的实例与步骤仍有部分唯一索引。
- `project_execution_plans`：固定 `start_index/target_index`（后者为排他上界）、`completed_steps,session_id,execution_json,generation,status`；每实例至多一个 ready／running／finalizing／quota_wait 计划。
- `project_plan_executions`：`run_id UNIQUE`，记录计划、当前尝试、source／额度代次、阶段、决定和严格释放；每计划至多一个未收口执行。

迁移事务复制全部旧列、ID、索引和自增序列，重复初始化幂等。schema 2 正常每个计划创建一组原 `tasks/runs`，多步及本次业务修复共用 Run；超时恢复另建 Run 并关联原计划。`runs.run_kind='project_iteration'`；来源题号只满足旧 `topic_no` 非空契约，原 `topic_id/batch_id` 留空，不加入旧路线或补充调度。无策略 schema 的旧批次继续单步 Run；内部 `create_batch(...,policy=None)` 保留该兼容入口，新 API 传入策略字典。

### 3. Contracts

**legacy 内容与版本**：内容 schema 1 的 `catalog.json` 为 schema 1；每个项目包含 `project.json`、可运行 `seed/` 和控制端 `verification/`。当前适配协议固定为 `python3 app.py`，逐行输入／输出 JSON。基线代码必须具有自己的业务核心；通用算法与启动脚手架可以复用。每步依赖紧邻前一步并属于明确阶段。

旧 100 个生成项目、生成器和参考运行时保持退役。当前源码 catalog 为内容 schema 2，实际版本和项目／场景／任务数量、原生适配与场景执行见后节。legacy 调度回归由 `orchestrator/project_test_content.py` 在临时目录构造夹具；源码变更不代表生产已部署，不删除历史发布及实例成果。

内容首次注册到 `BENCH_DATA/project-library/releases/<digest>`，旧批次固定旧版本。账号只复制 `seed/`，不挂载参考器或冻结验收目录。内容摘要覆盖相对路径和字节，不包括账号、mtime；拒绝链接、特殊文件及越界路径。快照上限为 128 MiB／10,000 文件，JSON 文件上限为 4 MiB。

**自动调度**：创建批次默认 `paused`，只建立元数据。schema 2 在创建时洗牌一次并持久化初始队列；池首批来自队头，完成或局部阻塞后从原队列补池。默认并发 2、活动池 3，Tasks 与项目共用账号真实容量并尊重 `PER_ACCOUNT_CONCURRENCY`；同实例只有一个在途写入执行。没有活动名额时不提前开始第四个项目。

连续通过默认 5 步后轮换，同一次 CLI 计划默认 2 步，实际范围受本轮余量和路线尾部截短，因此一轮为 2＋2＋1；修复不计步，每步首轮加最多两次修复。旧 schema 1 保持按内容阶段轮换和单步 Run。局部失败保留现场并切换；认证、身份变化或严格清理失败阻断批次。路线耗尽完成，不无限生成后续任务。

先填满初始并发窗口，执行严格收口后抽取计划补位间隔并持久化 `next_launch_at`；重启不重抽，一个截止只消费一次补位，等待不持有 CLI 许可。5h／7d 自设比例或当地时段只阻止下一计划及新恢复执行；当前已投放计划继续冻结范围，真实耗尽、认证及停止仍使用原强门禁，不新增 usage／模型探测。

批次状态为 `paused/active/pausing/stopping/stopped/blocked/completed`。暂停禁止新投放，已投放计划可以完成并验收；额度等待的原尝试保留，恢复沿用同一 Run。停止先持久化意图并增加 generation，终止在途执行；停止、阻塞、完成的批次不再启动，须另建批次。

**共同门禁与目录**：新类型通过 `_execution_workload` 映射到 `normal` 额度策略。窗口等待、账号信号量之后、凭据与环境准备之后、实际 exec 之前均复核门禁；不得创建独立模型调用通道。`can_start` 还核对账号可用性、冻结身份和父批次代次。

实例的 `workspace_relative/started_at` 初始为 NULL。只有进入实际启动才从控制端 staging 发布到 `environments/<environment_id>/projects/<alias>`；alias 由环境与实例 ID 固定派生。发布标记保存实例、基线摘要和目标路径，代次由尝试表及发布前检查约束。发布中断后核对已有归属，不删除或覆盖未知目录。后续步骤只复用原目录；暂停、阶段切换、完成、停止和服务重启均不清理项目文件。

**会话和用量**：schema 2 一个计划固定 session、cwd、版本／模型／effort，正常同一 CLI 进程和 tmux 逐步交接，不把独立 Run 归组冒充。提示只包含当前步骤、近期成果和有界失败证据。第 1 步通过、第 2 步半成品超时后，旧 Run 保留 timeout、计划为 1／2，目录和半成品保留；新 Run 接续原 session，只补原计划剩余一步。真实 quota_wait 使用原 Run／尝试，仅增加额度执行代次。schema 1 的新步骤／业务修复继续使用新主会话。

每步尝试保存自己的原生字节起止；已通过步骤的终点不能被最终 Run 释放覆盖，额度暂停也封存未完成步骤的边界。响应按 message ID 去重，排除 sidechain/meta。步骤不能重复累计整 Run 总量；缺起点、截断或无可靠统计时显示未知，页面不主动探测模型用量。

**验收与成果**：schema 1 仍须等待整次执行严格释放。schema 2 由 driver 在正常最终回复后提交候选通知，控制端核对 source／generation／阶段／session、实际 user 输入及 assistant 父链，再定向冻结完整作业树；稳定内核暂停证明成立后才封存并独立验收。接受检查点和下一决定同事务持久化，恢复同一个 CLI 后才投递下一步；最后一步通过仍须等该 Run 严格释放才收口。单有退出码零不能推进，验收不修改持续工作副本。

输入发送意图先持久化；确认丢失时先读实际原生 user，已消费不能重发。超时恢复若既无消费证据、又无检查点接受后尚未准备本步的明确证明，则阻塞实例。恢复前核对原 session 的持久字节位置和检查点清单／对象摘要；缺失、截断或冲突时保留现场并阻塞，不换会话、不重建 seed。

**决定文件交接**：`write_document` 默认仍为私有0600。决定专用调用传 `mode=0o640,owner=(0,1000)`，在临时fd完成归属、权限、完整写入和fsync后再replace，不能发布后才chown/chmod。已存在的普通、单链接文件若内容及root:1000 0640均相同，`_decision()`不替换inode；缺失或决定变化时重发。driver保留NOFOLLOW／NONBLOCK、普通文件及字节上限检查，只有fstat发现nlink=0时关闭旧fd重开，最多打开3次；硬链接、特殊文件、超大内容和持续替换仍失败，所有fd均关闭。

**停止与局部故障**：项目使用 `_stop_project_run()`，观察到终态或已认领stopping时返回 `{ok: true}`，不改写结果、不重复清理，也不生成释放证明；公开 `POST /api/runs/{rid}/stop` 对初始已终态请求仍400。长IO之后在短DB锁内重读，以quota_attempt及queued/running/quota_wait状态条件认领stopping并检查rowcount，只有认领者清理；竞争终态保留，代次变化拒绝409。清理后的stopped写入同样限定原代次及stopping状态。局部blocked导致的定向停止仍保留blocked及首次具体原因，不能泛化为人工cancelled；父代次变化／批次停止仍按取消处理。`is_executing`、最终释放代次及execution_error的门禁保持独立，认证／严格清理失败仍阻断批次。

整个本次 CLI 计划共用工作超时，逐步通过和修复均不重置；管理暂停及验证另有有界时间。tmux 交互 shell 启动前 `set +m`，防止冻结／恢复后 shell 作业控制把终端改回规范输入，导致下一步不能被 CLI 消费。

验证容器复用同批 account 镜像，显式覆盖入口、UID 1000、无网络、只读根、无账号 HOME／凭据／Docker socket；候选只读挂载，复制到临时可写目录运行。默认 30 秒，内存 256 MiB、PID 64，输入及输出有界。控制端比较行为结果并回归基线和此前全部已接受能力，不能信任程序自行宣告通过。

`validation_status` 为 `pending/running/passed/failed/error/cancelled`。程序超时／错误输出属于业务失败；验证基础设施故障最多在本地验证两次，不投递模型修复。通过后事务同时校验父状态、generation、步骤下标和预期 checkpoint，并依赖唯一约束防止重复接受。失败快照和最后通过版本同时保留，历史文件通过清单读取，不能用当前目录冒充旧成果。

**集成与交付**：项目 API 的五类资源必须同步加入 `cc2api/src/service/runtime_bridge.rs` 白名单，保留内部路径和编码穿越拒绝；不得扩展鉴权豁免。`#projects` 复用 `RUNTIME_BASE`、API helper、主题变量及转义；离开页签关闭 EventSource，推送重绘保留滚动位置和路线展开状态。

批次调度提示按七种状态分别显示：仅active使用实时wait_reasons或自动推进提示；暂停、收尾、停止、阻塞及完成各自说明。`next_launch_at`只有active且仍在未来时显示，终态不显示等待启动或失效投放时间。

control 镜像的项目库、`images/v3/Dockerfile.dockerignore` 放行项、`deploy/v3/manage.py` 的源码快照列表须同步。`PROJECT_LIBRARY_DIR` 可覆盖内容路径，容器默认 `/repo/project_library`；当前 catalog 损坏只使目录／新建准入返回 503；历史从冻结 release 读取，普通题库保持原入口。账号删除引用计数包含新批次，不能将尚无 run 的项目批次变成孤儿。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| `account_id=true` 或键列表类型不合法 | Pydantic 422，不写批次 |
| 项目选择为空／重复／未知、名称非法、账号不可用 | 创建返回 400，不建目录 |
| 新模式未就绪或内容损坏 | 项目 API 503，旧模式继续可用 |
| 目录／批次／实例／尝试不存在 | 对应查询 404 |
| 恢复已停止／阻塞／完成或身份不符批次 | 409，保留成果 |
| 从旧 task 再次运行、旧 run 人工续聊项目步骤 | 409，引导通过项目批次推进 |
| 窗口／额度等待、暂停、未通过准备后门禁 | 不发布未开始的项目目录，不绕过门禁 |
| schema 1 未严格释放／schema 2 无匹配暂停证明 | 不封存、不验收、不投递下一步 |
| schema 2 最后一步通过但 Run 未释放 | 保持 finalizing，同实例不得开始下一计划 |
| 合法原子替换使已打开fd的nlink=0 | 关闭旧fd有限重开；超过3次或其他文件校验失败则拒绝 |
| 内部停止已终态／已认领停止的Run | 幂等确认；结果和释放证明保持，公开初始终态仍400 |
| 停止认领前出现终态／新额度代次 | 保留终态且不清理；新代次拒绝409，不停止新执行 |
| 局部blocked定向停止执行 | 保留首次原因，严格释放后健康项目继续，不能改成cancelled掩盖故障 |
| 会话／检查点缺失、截断或输入消费不确定 | 保留代码与失败现场，阻塞该实例，不盲发或重建 |
| CLI 退出正常但行为失败 | 不推进，在原目录有限修复；用尽后阻塞实例并切换 |
| 验收期间停止或旧 generation／checkpoint 回包 | 不接受结果，不增加进度 |
| 已发布目录缺失、归属不明、链接或快照损坏 | 保留现场并阻塞，不重置 seed |
| 请求历史文件越界或文件不在清单 | 404；不读任意宿主路径 |

### 5. Scenarios and Examples

- 正常：创建 `{ "account_id": 1, "name": "本地迭代", "project_keys": ["project-001", "project-002"] }`，两个实例路径均为空。实际启动后才创建各自目录；账号有容量时两个项目真正并行，每个计划在同一个 Run 内验收两步。
- 边界：一轮 2＋2＋1 通过后轮换；第 2 步半成品超时显示 1／2，原 timeout Run 不变，恢复 Run 只补该步。暂停和额度等待保存进度，停止后目录仍可检查。
- 错误用法：每个新 Run 重新复制 seed，或直接用退出码零推进步骤。正确做法是按实例复用目录，按 schema 取得严格释放或逐步定向暂停证明，再验收冻结候选。
- 错误用法：用整个共享 cwd 的 JSONL 计作本轮 token，或把参考路线通过称为真实模型完成。正确做法是使用 run 字节边界；真实模型通过率和用量单独观察。
- 边界：决定文件重复发布保持同一inode，文件缺失则补发；另一个连接先把Run写成success时，停止请求不能覆盖成stopped或执行第二次清理。
- 错误用法：replace后才给决定文件改权限，或为处理nlink=0而接受所有链接。正确做法是发布前设置权限，仅对已打开旧inode归零有限重试，继续保留全部校验和阶段归属核对。

### 6. Tests Required

- `python3 scripts/validate-project-library.py --root <本次测试夹具目录> --all`：数量、依赖、摘要；全部 seed 真正运行；待开发步骤不能在基线通过；所有测试参考断言可达到。该命令仅用于显式 legacy 夹具；当前正式根静态校验输出 3／13／20，新内容原生校验使用 `validate-project-scenarios.py`，不将临时夹具回写为正式内容。
- `test_project_iterations.py`：同账号不同批次及不同账号基线一致、修改隔离；100 元数据零目录；两步累积、失败修复与旧能力回归；三项目阶段轮换返回；重复接受、停止竞争、额度暂停恢复及重启；认证／清理失败阻断；不可变历史、路径和主日志边界。
- `test_project_plans.py`：严格策略、实际容量 1、固定随机队列、2＋2＋1 轮换、共享容量与持久间隔；同 Run 两步、逐步 token、业务修复、停止竞争、重复决定及父链乱序；1／2 超时接续、原 Run quota_wait、检查点／会话缺失与截断、确认丢失和禁止盲发；旧结构主键／索引／序列幂等迁移。
- 文件／停止回归：发布边界实际UID1000读取、相同决定inode不变、缺失补发、普通文档0600；open与fstat间替换、持续替换上限、非法文件与fd关闭；初始终态／SQL认领前独立连接终态／新代次／清理中终态不覆盖，不重复清理、不伪造释放，局部blocked首次原因与健康补位。
- `ProjectVerifier`：独立 Docker 正例／反例、程序超时与基础设施错误区分；控制端 umask 不影响 UID 1000 读取候选。
- `deploy/v3/run_local_verification.py --manifest <清单> --project-iterations-only`：合成 CLI 经过真实 Scheduler、driver、会话、清理和 Docker 验收的两步闭环。不得当作真实模型能力证据。
- `deploy/v3/run_local_verification.py --manifest <清单> --project-scheduling-only`：真实 Docker／driver／tmux 中两个 CLI 重叠、冻结 A 时 B 继续、同 Run 两步及 60 秒真实 timeout 后只补剩余一步；Tasks 两 CLI 和既有 passthrough 长连接跨补位／清理保持。多个验收入口顺序创建独立网络，避免测试子网竞争。
- `deploy/v3/verify_stack.py --manifest <清单> --browser --project-iteration`：真实 UI/API/SQLite，目录等待与重启保留、XSS、SSE 状态保持、1280/390px 明暗主题。
- `--project-scheduling-only`还须验证定向局部阻塞后兄弟及原队列后续项目继续。`--project-catalog-only --evidence-dir <新目录>`为可选100×20长测，保持默认10秒稳定等待并独立对账；部分运行不能记为全库通过。中断先停止本次标签下的写入容器，再清临时目录，保留证据及精确清理结论。
- 原 `--run-boundaries`、`--topic-followups` 分别回归；新管理桥运行 `cargo fmt --check` 与 `cargo test --locked`，保留内部路径拒绝断言。

## Scenario: 内容 schema 2 的真实项目多场景任务与 policy 3

### 1. Scope / Trigger

- 修改 `project_scenario_content.py`、`project_scenarios.py`、`project_evaluation.py`、`project_scenario_usage.py`、`project_review_runtime.py`、`project_native_regression.py`、原生验证器、场景 API／页面或正式内容时适用。账号角色、租约、唯一凭据所有者仍遵守 account-runtime-v3；旧线性模式按前节版本读取。
- 当前源码内容为 `real-project-scenarios-v37-en`：保留原10项目／45场景／107任务，三个阶段分别新增30仓／126场景／244任务、30仓／134场景／192任务、30仓／121场景／183任务，合计100项目／426场景／726任务，其中689个非修改任务、37个修改任务。第三阶段新增180个非修改任务、3个修改任务；数值来自实际manifest，不是未来阶段的固定配额。本地内容通过不代表已部署。任务类型固定 `understand/consult/diagnose/plan/modify`，不要求每项目20步。内容就绪、本地模拟机制、真实模型完成及生产部署分别计数。

### 2. Signatures

```python
ProjectIterationManager.create_batch(account_id, name, project_keys=None, policy=None, scenario_entries=None)
initialize_scenario_schema(connection) -> None
normalized_scenario_policy(values, project_count, account_limit) -> dict
ProjectVerifier.verify_native(candidate, project_root, specification, environment_root, profile,
                              *, answer='', regression=False) -> dict
ProjectScenarios.finish_captured_quota(run_id) -> bool
observed_model(directory, response, session_id) -> str
serial_review_limits(memory: str, swap: str = '0') -> tuple[int, int]
ProjectReviewRuntime.pending(account_id: int | None) -> bool
ProjectReviewRuntime.serial_state(row: dict) -> dict | None
ProjectReviewRuntime.serial_layout(row: dict, cli) -> dict
ProjectReviewRuntime.prepare_serial(job: dict, cli, layout: dict) -> None
ProjectReviewRuntime.restore_serial(job: dict) -> None
ProjectReviewRuntime.clear_serial(job: dict) -> None
_suite_paths(suite: dict) -> tuple[Path, Path]
_bind_source(project: Path, import_root: Path, cleanup: ExitStack, *, console: bool = False,
             distribution: tuple[str, str] | None = None,
             executables: list[tuple[str, str, str]] | None = None,
             entry_points: dict[str, dict[str, str]] | None = None,
             license_expression: str | None = None,
             project_urls: dict[str, str] | None = None,
             console_scripts: dict[str, str] | None = None,
             metadata_fields: dict[str, str] | None = None) -> dict
_subtest_results(reports: list[dict], node_ids: list[str]) -> list[dict]
_subtest_contract(subtests: list[dict], format: str | None = None) -> list[dict] | dict
_subtest_evidence(directory: Path, subtests: list[dict]) -> dict
_process_pool_workers(workers: int) -> Iterator[None]
_fixture_aliases(baseline: Path, project: Path, suite: dict) -> list[dict]
_build_native_extension(project: Path, suite: dict, environment: dict, evidence: Path, timeout: int) -> dict
_system_libraries(specification: tuple[str, str]) -> list[dict]
source_snapshot_ignore(directory: str, names: list[str]) -> set[str]  # deploy/v3/manage.py
_public_source_directory_digest(root: Path) -> str  # deploy/v3/manage.py
restore_upstream_checkout_bytes(root: Path) -> list[str]  # deploy/v3/manage.py
```

受控回归 CLI 为 `project_native_regression.py --project <SUITES中的key> --baseline-root <原版> (--freeze-baseline-contract <新合同> | --contract <冻结合同> --candidate-root <候选>) --evidence-dir <空目录> [--timeout-sec 600]`，超时范围为1～1800秒。校准与候选回归互斥，不能覆盖既有合同或非空证据目录。

| API | schema 2 内容的公开契约 |
| --- | --- |
| `GET /api/project-catalog` | `content_schema,version,digest,scheduling_defaults,projects`；项目有 `scenario_count/task_count`。 |
| `GET /api/project-catalog/{key}` | 一个项目的白名单摘要，附场景及任务 `id/kind/goal/requires`，隐藏 prompt／分支／rubric；不返回目录顶层 version/digest。 |
| `POST /api/project-iteration-batches` | 原账号／名称／project_keys及严格整数策略；`scenario_entries` 为 `{project_key:{scenario_id:entry_id}}`，省略选固定默认入口。DTO `exclude_unset=True` 后依内容版本归一默认。 |
| `GET /api/project-instances/{iid}` | `content_schema=2`，场景、选中任务、结果／phase、candidate/review预算、实际Run与评测状态、逻辑plans；不复用 next_step_index 表示任务进度。 |
| `GET /api/project-instances/{iid}/scenario-tasks/{tid}/attempts` | 实际业务尝试及 candidate／review 执行；tid 是数据库任务ID，与稳定 task_key 分开。 |
| `GET .../scenario-tasks/{tid}/artifacts`、`GET .../file` | 可选 `evaluation_id` 定位固定回答；file另需清单内 `path`，有界读取；强制归属 iid/tid。 |
| `GET /api/project-instances/{iid}/usage` | `tasks` 按 candidate/review 角色累计、`by_kind` 分类；输入／输出／缓存读写分别统计，已知小计带覆盖标记，全未知为null。 |

沿用原项目资源前缀、Cookie、SSE与桥白名单，不增加鉴权豁免。新持久表均由 `init_db()->initialize_scenario_schema()` 幂等创建，不改写旧行／ID：

| 新表 | 关键身份／持久边界 |
| --- | --- |
| `project_scenario_instances` | instance＋scenario_key唯一；entry_key、独立workspace/session、seed与当前accepted checkpoint。 |
| `project_scenario_tasks` | 场景＋task_key唯一；selected、kind、phase、turn_no、attempt_count、infra_recoveries、input／accepted checkpoint。 |
| `project_task_attempts` | task＋attempt_no唯一；实际消费才创建，最多3，结束原因独立记录。 |
| `project_task_executions` | run_id唯一；task/attempt/plan、candidate/review、generation、session、delivery及review逻辑尝试。 |
| `project_execution_sources` | execution＋quota_attempt＋source唯一；逐代原生起止、start_permitted、work文件及真实released_at／execution_error。 |
| `project_task_deliveries` | task＋phase_key唯一；固定prompt摘要、真实input_key和consumed_source_id，不盲重发。 |
| `project_evaluation_jobs` | source＋response_key＋version唯一；回答／输入／rubric／candidate摘要、evidence_json、机械／语义结果、评审恢复及回答预算。 |
| `project_work_segments` | source＋segment_seq唯一；boot／monotonic、reserved／confirmed、高水位与settled／uncertain。 |
| `project_scenario_plans` | 场景至多一个未结束逻辑计划；明确task_ids／passed_ids，不按数组前缀猜范围。 |

### 3. Contracts

**内容与离线环境**：内容 schema 2 项目必须固定上游HTTPS GitHub URL、40位commit、seed内许可、seed_digest、environment及可变scenarios/tasks。entry列必要task_ids；branch只选固定披露材料／setup／同场景activate_tasks。requires精确声明answer或code依赖，首版仅同场景无环，code仅引用modify。公开materials与控制verification隔离；setup来源固定，目标仅app/。每项目源码对象上限128MiB／10000文件；环境wheel独立存放，逐制品hash、精确requirements及Python版本冻结，business/regression资源分开，不能把venv放进源码快照。

**材料与评审证据**：首问尚未消费的隐藏复现或业务决策，不能提前写成通用 rubric 的具体事实，也不能无条件放入 `source_evidence`。披露判断依据实际消费对话和公开源码。`allow_candidate_evidence=true` 不仅允许引用候选文件，还会让 satisfied／violated 判定必须给出证据；只读任务没有候选修改文件，不能以空静态 evidence 加该 flag 构造无法满足的规则。确有文件交付的修改任务仍须按冻结清单引用 `candidate:<path>`。

**模型输入与页面语言**：正式内容的 `task.prompt`、`branches[].when`、rubric 的自然语言规则、业务材料中的指令与说明，以及候选的材料包装、quota／timeout／infra 接续、补充与修正、`review_prompt` 均使用英文。`title/category/description`、场景及任务 `goal` 是中文页面字段，`scenario_summary(..., include_tasks=True)` 的浏览项目与路线投影保持中文。固定业务字面、原始代码、报错、帮助与证据原文不翻译；例如英文首问要求 status 为 `已校对`，不能把该验收值替换成英文，也不能仅凭出现汉字拒绝原始资料。语言修正发布新内容版本与评审版本，由内容树重算摘要；不原地改写已冻结的问题、回答或历史发布。schema 2 的通用结构校验不自动推断语言，正式内容需另行逐项核对指令与业务数据边界。

**发布与状态**：新批次paused且只写元数据，首次实际启动才物化场景独立工作区／候选session。同项目至多一个候选写入；逻辑计划默认2任务、通过5任务或局部收口轮换，活动池默认3，共享并发最多2并受账号真实容量约束。任务通过、代码接受、场景收口与批次运行完成分开；只读任务不会创建代码检查点，completed可包含明确失败／耗尽／受阻。

**新任务输入与代码依赖接受来源**：未声明 code 依赖的新任务从场景已接受状态开始；尚无接受代码时使用初始基线及启动前冻结的入口材料。旧任务未接受改动封存到交接备份，不进入新任务输入；同任务 ready 标记接续保留当前半成品。code依赖必须对应前置task的passed与accepted_checkpoint_digest，并定位该摘要的passed评测作业。`project-artifacts/task-inputs/<task_id>/code-dependency.json` 保存dependencies作业ID→摘要、base_checkpoint_digest、base_checkpoint_job_id及ready／replacing状态。多依赖须沿评测evidence中的 `parent_code_job_id` 属于同一已接受父链；不能用摘要相同折叠回退后的不同分支，更不能猜测合并。工作区非所需版本时先保存原现场，再从已核对对象物化；交接中断受阻。候选evidence冻结 `parent_code_digest,parent_code_job_id,input_checkpoint_digest`；授权范围验收使用该作业冻结输入，不能使用后来变化的任务checkpoint代替。

**严格释放与接受**：真实父链／输入消费／source/generation核对后定向冻结、封存回答和候选，并先持久waiting_release与complete决定。driver正常退出，精确来源严格释放后才排机械验收；需要评审时经原Scheduler／normal额度及 `claim(shared_cli=False, exclusive=False)` 创建project_review，同账号其他CLI互斥且不排空API，候选不持名额等待评审。评审结果封存后也须严格释放，CAS核对父generation／状态、最新作业及未收口执行后才接受或披露／有限修正。重复候选／评审通知重放已落决定，不重复freeze；迟到旧代结果不推进。完整输出遇quota／重启只续验收，不再重问；旧Run终态保留。

**同实际模型评审**：场景冻结原账号身份、CLI版本、effort和配置execution_model（空串也是合法配置快照）。候选封存时从已核对主assistant精确原生位置读取 `message.model`，存evidence `resolved_model`；私有评审用该值作 `CLAUDE_MODEL_OVERRIDE`，评审结果再核实际原生模型完全一致。禁止因CLI默认／全局设置变化静默换模型，也不调用模型清单探测。评审使用独立session／PID／mount／HOME／input／日志，原账号netns、AT-only副本和唯一刷新所有者；候选无法从其共享目录读取隐藏材料。

**串行资源交接**：新环境不预留常驻评审份额；`serial_review_limits` 返回普通三角色预算中CLI剩余RAM，MemorySwap与Memory相等，额外swap只归固定CLI。旧schema1预留布局核对原固定CLI的实际限额，仍可借用原账号总预算扣除network/sender后的RAM，固定CLI配置不改写。评审CPU沿原固定CLI的有限NanoCpus，公共角色合计不得超 `V3_ACCOUNT_CPUS`（默认2）；私有容器仍为UID1000、根只读、PID128、tmpfs64MiB。

评审在环境锁内认领非共享CLI并确认无未知进程，先持久意图再停止固定CLI，reload确认为exited/dead/created后才能创建私有容器。清理始终先停止并核验私有容器，再恢复同一固定CLI并核验画像／公共角色，最后退租、删除交接记录及执行记录。网络和sender全程保持，API可继续使用原发送连接。普通CLI从串行状态检查、画像探针到认领连续持同一环境锁，版本安装在锁外；共同认领边界对全部同账号活动批次的当前generation、evaluating且review_ready/review_queued工作优先，paused和旧代不阻新作业。

`runtime/execution.json` 保存非共享评审及 `resource_mode='serial-v1'`；历史无mode评审仍按旧清理路径读取。root私有0600的 `runtime/project-review-serial.json` 用atomic_json/fsync发布：

| 字段 | 归属与边界 |
| --- | --- |
| schema、environment_id、environment_generation、container_id | schema=1，绑定原固定CLI及当前环境代次 |
| source、run_id、review_intent | 绑定本次执行；intent为64位十六进制摘要 |
| phase、cli_was_running | prepared/cli_stopping/cli_stopped/review_running/review_stopping/cli_restoring；本次负责恢复为true |
| cli_limits | 原Memory、MemorySwap、NanoCpus、PidsLimit有限正整数快照，恢复前核对实际配置 |
| review_limits | 本次Memory及MemorySwap有限串行预算 |
| review_container_id | 创建ACK可用时写入；ACK丢失按原intent标签找回 |

有效交接期间 `ensure` 只提供原API环境，不唤醒固定CLI；CLI准备返回RuntimeBusy等待。恢复失败、未知running孤儿、代次／限额冲突或缺少执行登记保留记录和占用；串行执行仍登记但交接记录丢失时，只有原CLI实际运行且私有容器停净才允许退租。回退前必须停净私有评审并完成原CLI恢复；旧版缺少串行协议，不能删记录或在回退后承诺普通布局仍可评审。

评审包冻结完整已消费当前任务对话、回答、rubric、真实源码事实、程序结果及实际交付candidate_files（逐对象摘要核对），总上限512KiB，超限受阻不截断。输出最多64KiB的单JSON，身份字段为 `job_id/task_id/turn_no/response_digest/basis_digest`；decision限disclose/pass/fail/uncertain，逐criterion恰好一次，证据必须在冻结清单且candidate引用获显式许可，反馈限白名单。程序失败不能被语义覆盖；合法uncertain直接受阻，不重抽。modify仅在native及适用regression通过后接受；声明semantic的交付要求还须评审。

原所有者刷新待办位于 `project-review-owner-refresh/<account_id>.json`，绑定 request_id／原身份／environment_id与generation／被拒AT摘要。旧身份、旧环境或原所有者已发布不同且未过期AT的请求不阻新准入；新请求把旧记录归档为superseded并保留previous_status。当前被拒AT的error仍阻断；双参数 `refresh(account, request)` 在原owner锁内重读身份／环境／request_id，迟到写回用request_id CAS，不能刷新或覆盖新请求。私有作业未停净时保留holder及创建意图，未知running孤儿阻止第二评审。

**预算与恢复**：policy3候选 `timeout_sec=600`、`task_budget_sec=1800`；业务首轮加最多2次继续／修正，实际输入消费才扣，正常澄清与额度接续不增业务尝试。`review_timeout_sec=180` 限同一逻辑评审跨Run/source累计；同回答最多首次＋1次错误重评且回答总上限为其2倍；`review_budget_sec=720` 限任务全部回答轮次累计。单次领取三层剩余量最小值，infra恢复对业务任务／冻结回答各最多2次，不重置余额。候选及任务累计、任务review累计公开范围60～86400秒；review单次60～600；实际剩余不足公开最小值也不能向上补发。boot＋monotonic片段启动前预留，退出按真实高水位结算，尾段不明保留预留且受阻，不伪造耗时或清零。token按精确source字节区间、session/message去重，统计complete与任务passed不同。

**原生验证**：`verify_native` 在同批account镜像、UID1000／network none／只读根／无账号凭据内执行；源码、baseline、offline、控制脚本与输入只读，临时运行树隔离。离线准备阶段证明与业务时限分开；pip使用`--no-index --no-deps --no-compile`，避免重复编译缓存占满受限tmpfs，不缩减实际依赖或测试。环境error只本地有限重试，不投递业务修正。工程回归从固定baseline恢复上游适用集合，核Python／插件／baseline与节点contract，业务通过后真实执行，不只检查声明或退出码0。新原生验证的并发名额覆盖容器清理；清理无法确认时保留阻断记录。内容复制、Docker忽略与源码快照须一致；Typer及Decouple固定公开.env、Docutils固定.log与target夹具按精确路径及文件／完整目录摘要保留，未知文件和链接仍拒绝，不放开其他环境文件或构建产物。

**原生套件布局与校准**：`SUITES.package` 是可导入模块名，`implementation_dir` 默认按模块点号转路径，`import_root` 默认为 `.`；两路径必须相对、无 `..`，实现路径只允许导入根拼接模块路径或对应`.py`单文件。Jinja 固定 `package=jinja2,implementation_dir=src/jinja2,import_root=src`；只叠加实际实现，拒绝实现及父目录链接，恢复baseline测试／配置并拒绝新增pytest控制声明。`test_roots`显式指定实现包内的固定测试与数据，候选不能替换PETL／Toolz／JSONschema／Cerberus包内验收。实际import必须落在受控测试树。新套件在目标镜像收集非空、无重复的真实节点并完整执行，冻结schema／project／baseline_digest／python／plugins／nodes；候选逐节点及结果精确匹配合同。旧三个suite保留原硬固定计数和默认布局。每个新增小批的私有回归副本与当时共享实现逐SHA一致，后续新增套件不原地升级此前已冻结的私有脚本。

**原生框架与补充入口**：`framework`缺省为pytest，Python-Markdown／Docutils／Icecream使用上游unittest发现，Dpath使用真实nose2发现、结果事件及官方JUnit插件；不能以unittest发现替代nose2的函数测试。冻结合同额外保存框架与原始skip原因，结果、导入来源、XML逐项核对，夹具异常与未知结果不能当通过。ConfigObj的`supplementary`分别执行上游脚本及模块doctest入口，保留原初始化、逐例source／want摘要、flags与结果，不能只调用testmod而漏掉脚本初始化。动态导出示例从隔离原版解析并恢复到候选；类方法写回底层函数，Toolz动态文档描述符只更新classval，保留实例行为。PETL的收集阶段skip单列`collection_skips`冻结身份／行号／原因；JUnit元素数等于主项加收集skip，不混为执行后的skip。

**固定工具、元数据与夹具**：Click离线less工具先核制品路径／SHA，再排他复制到本次独占venv；`distribution`只生成已核原版名称／版本的dist-info，`entry_points`与`license_expression`从冻结pyproject读取，不安装第二份候选实现，退出清理。Docutils的`cwd`为固定相对测试目录；`fixture_aliases`只把已核Git链接blob目标在私有运行树复制成普通数据，原seed保留目标文本。别名、目标、父目录越界或链接均拒绝；不能修改原生预期数据制造通过。

**第二阶段原生入口与元数据**：Simplejson沿官方`simplejson.tests._cibw_runner`执行C／纯Python两轮及index.rst；在本次`/work`私有树真实编译候选扩展，并逐例核编码、解码、扫描接线及扩展来源。节点仍恰为id／kind／outcome，身份以实际mode＋原始ID区分，`unittest_contexts`保留并精确比对；官方skip表只按身份排序，不改变其集合。Marshmallow的固定两项当前时间参数仅按原参数位置规范ID，原值另存`parameter_identities`；不改输入或时钟。Babel真实重复doctest节点按occurrence区分，原始身份／次数／父对象保留在`duplicate_identities`；目录收集skip仅允许已列目录且存在原conftest。sqlparse仅允许逐名冻结的原版非strict XPASS，身份增加、丢失、替换或新XPASS均拒绝，候选节点结果仍必须逐项匹配。

私有分发可从固定pyproject读取脚本／链接／描述；legacy Babel则显式冻结真实入口字典，不猜测不存在的`project`表。命令排他创建于独占venv，候选实现仍来自受控`.pth`；Summary／Author-email仅允许非空单行白名单值，Project-URL保留原声明顺序。Tk共享库仅从已核离线制品逐SHA读取，版权随制品保存，不改系统安装。Dateutil保留warnings-as-errors，通过实际pytest-cov登记no_cover；时区仅取冻结离线tzdata。业务与回归预算分别实测，Packaging的1024MiB／600秒回归不扩展其256MiB业务或账号容量；旧四十仓冻结私有runner不原地更新。

**第三阶段原生扩展与只读夹具**：Pyrsistent、Python-Constraint和Wrapt只在本次`/work`受控树从实际候选C／Python源码强制构建；setup、配置、测试和构建脚本从固定baseline恢复。`extra_implementation_files`仅允许原版已有的精确路径，拒绝缺失、链接、越界及pytest控制注入。`native_modules`逐个核当前解释器EXT_SUFFIX、实际路径和SHA，不能以同名Python模块冒充扩展；另核Pyrsistent／Wrapt默认对象确实绑定C实现。Cython只读docstring与原文相同时不重复赋值，变化仍须恢复或拒绝。Pendulum的固定Rust原件明确`rebuilt_in_current_run=false`，本轮分别核Rust绑定与完整Python模式，不声称重建Rust或允许未重建的源码修改。

`_system_libraries`只接受固定清单SHA及`artifacts/tk-libs`、`artifacts/gettext-libs`、`artifacts/graphviz-libs`内同一目录的普通成员，逐成员SHA校验，拒绝跨目录混用和链接；LD_LIBRARY_PATH来自实际已核清单父目录。Graphviz工具、插件、对应版权及完整源码原件随环境封存。仅Pendulum的两条固定时区fixture启用`fixture_symlink_semantics`：核原Git目标文本、内部普通目标及SHA后，在独占私有测试树恢复相对链接；正式seed及只读baseline保持原link blob文本，其他别名仍复制普通文件。不得创建外部目标或链接父目录。

**dotenv CLI与第二批套件**：dotenv固定 `package=dotenv,implementation_dir=src/dotenv,import_root=src`；TOMLKit／sqlite-utils／Tenacity导入根为`.`。sqlite-utils显式启用已冻结Hypothesis分发的 `_hypothesis_pytestplugin`，不依赖关闭autoload后消失的隐式插件。Typer与dotenv的子进程绑定只写`/work`下本次独占venv的纯路径`.pth`，purelib须位于该venv，系统或外部共享解释器拒绝。dotenv额外以排他创建生成该venv `bin/dotenv`，固定目标 `dotenv.__main__:cli`、0755；已有入口或链接拒绝覆盖。路径文件及新入口注册退出清理，直接CLI测试实际导入受控src；不能用安装发行包或仅`python -m`代替原生可执行入口。

**真实子测试合同**：仅显式`subtests=True`的套件冻结子项；pytest取真实`SubtestReport.context._to_json()`，unittest取原生addSubTest／addSkip回调。条目为`parent_nodeid,ordinal,when,context,outcome`，context恰为`msg`（null或字符串）及`kwargs`（字符串键／序列化字符串值）。同父节点按实际出现ordinal保留重复context，不折叠；仅允许已收集主节点的call阶段。schema1合同新增可选subtests，旧suite保持原行为；启用套件的候选合同缺少／为空须拒绝，候选完整子项与冻结集合逐项相等，失败／xpass不能被父项passed遮蔽。unittest子项跳过可能省略父项addSuccess，须保留父项已执行与各子项skip；子项失败仍使父项失败。主节点、子项、收集skip和JUnit元素分别对账，不能用suite汇总tests属性替代。Tenacity真实185主项／15子项、XML185元素及汇总200是独立口径，不重复计数。

**大集合子项表示**：`subtest_contract`未指定时继续冻结及输出原完整列表。显式`sha256-v1`保存完整有序记录的数量及SHA；仅SQLGlot使用`sqlglot-subtests-v1`，保留完整父项、阶段、上下文、结果和重复次数，只移除观察ordinal并排序多重集。唯一地址规范化限`tests.test_expressions.TestExprs.test_convert`中完整匹配的PointClass默认repr；SQL十六进制字面、其他msg及kwargs不得改写。摘要头为`format,count,sha256`，全部实际子项仍先经过既有校验及合法结果检查，再逐SHA匹配，不能采样、去重或忽略失败。

原始观察全部写入私有`subtests.json.gz`，元数据为`file,sha256,count,bytes,expanded_bytes,observed_order_sha256`；拒绝覆盖。校准时将完整原件及SHA封存进项目verification，运行结果只返回摘要头和原件元数据，保持4MiB合同及2MiB产品输出上限，不把完整大列表塞进stdout。独立审计须同时核冻结控制器、完整基线原件、数量、父项及全量摘要，旧列表比较不变；从已核源码字节加载控制器，避免冻结输入中的pyc读写。SQLGlot原生发现和loader不改，只将缺省或显式None的ProcessPoolExecutor默认并发设为2，显式非None参数保持并在finally恢复构造器；完整原测试仍全部执行。其业务512MiB／30秒、回归3072MiB／360秒是当前镜像实测值，不增加账号资源或平台上限。

**上游文件表示与运行取证**：来源清单同时记录Git blob及mode；内容快照禁止真实symlink时，上游文档link blob可按原目标文本字节存普通文件，明确表示差异并保留完整许可／文档原件，不能伪称原类型未变。普通上游执行位在源码Git／Docker交付保持；既有快照只按路径／字节／大小封存并统一物化0644，不承诺模式保真。TOMLKit固定测试子模块独立来源／许可、完整展开，不能用空目录或Python3.12 TOML1.0解析器否决TOML1.1语料。私有评审挂载检查先将runtime私有根按data相对路径映射到host_data，再与Docker Mounts.Source双向比较父子重叠，不能跨命名空间直接比路径。source.created_at／released_at包含启动配置及释放后取证收账，不能当精确holder占用区间；实际工作窗口、进程清理、holder采样和源码门禁分别报告，缺逐holder事件不得声称完整时序已重建。

**Git 字节保真**：正式 `project_library/**` 使用 `-text eol=lf`，本任务冻结研究证据使用`-text`。嵌套上游`text=auto`继承LF导出规则，显式binary仍保留字节；不修改上游属性文件。Dateutil的NEWS／docs/make.bat另被上游显式指定CRLF，普通Git检出可能转换。官方CI使用manage.py build，该入口只在临时源码副本调用`restore_upstream_checkout_bytes`：仅这两个精确路径的已核原blob SHA或整份CRLF转换SHA可接受，全部预检后恢复原blob字节；未知修改、文件或父目录链接拒绝，执行位不变，缺少整个项目时不增文件。Git证据沿真实checkout-index后使用相同恢复函数，分别记录`raw_checkout_bytes_equal`与`production_source_restoration`，不得把恢复后相同说成原始检出相同；Docker COPY验证正式恢复后的完整树。

Dynaconf的76份和Flask的一份固定公开.env原件沿既有精确路径／SHA与Docker逐文件放行列表交付，不放开其它环境文件。python-frontmatter固定`seed/library/AGENTS.md`按来源清单精确保留，本地工具AGENTS.md仍忽略。提交前从索引导出内容，按上述生产恢复规则逐文件核清单／字节／执行位，并重新加载`ProjectLibrary`比较摘要；工作区校验不能替代Git导出校验。上游空白、原始帮助输出及补丁上下文原样保存，原创实现仍做空白检查。

### 4. Validation & Error Matrix

| 条件 | 结果与边界 |
| --- | --- |
| 新内容省略预算／显式合法预算 | 依内容选择600等新默认／按原值冻结；不能被DTO旧1800覆盖。bool/string/float/null预算与未知字段拒绝。 |
| 旧内容提交新专用预算或入口字段 | 明确拒绝；旧无schema／policy2语义保留。 |
| 当前catalog损坏，历史release完整 | catalog／新建503，历史批次／回答／文件仍按固定release可读。 |
| 缺依赖、跨场景依赖、环、code引用非modify | 内容准入拒绝；未选分支不计本次必要任务分母。 |
| code依赖无接受作业／父链不一致／交接replacing | 保留现场并受阻，不以当前cwd或相同摘要猜测继承／合并。 |
| 候选完整但未严格释放、评审未释放 | 保持等待，不能接受、重问或开始相冲突执行；容量1也不持候选holder等待评审。 |
| 已有CLI／有效交接时的评审准入，或待评审时普通CLI认领 | admission等待且blocked=false／RuntimeBusy，不把竞争标为业务失败；已认领作业可完成。 |
| 固定CLI停止未确认、未知运行评审或原配额／代次冲突 | 不创建下一私有评审或恢复CLI，保留占用与持久意图。 |
| 交接记录丢失且固定CLI仍停止 | ValueError，保留执行记录；不能假报恢复或释放。 |
| 完整候选／评审输出后quota或重启 | 只续收口与验收，保留Run中断事实，不重复模型输入或计量。 |
| 新source未许可／许可后尾段不明 | 前者有持久证明可结算未投递；后者保留预留并受阻，不盲给新预算。 |
| 原生准备异常／业务断言或已进入业务后的超时 | error／failed，前者本地有限重试，后者可用有限业务修正。 |
| suite 模块／相对路径不匹配、实现或父目录链接、候选错导入安装库 | 拒绝回归；候选源码违规为 failed，不借环境重试接受。 |
| 冻结合同来源不符／Python或插件漂移／空节点或节点结果不符 | 拒绝；环境漂移须重新校准原版，候选不能靠删测试或退出码零通过。 |
| dotenv系统或外部venv／已有CLI入口；Tenacity缺失子合同、非法父节点或子项不匹配 | 拒绝；不覆盖未知入口，不以主项pass或XML汇总替代子项证明。 |
| nose2函数用例遗漏／框架漂移、包内测试被改、补充doctest或收集skip合同缺失／变化 | 拒绝；必须沿原入口完整校准，不能靠换发现器或少跑节点通过。 |
| 固定工具SHA不符、源码别名目标越界、公开夹具多文件／改字节／换链接 | 拒绝；不借精确原件例外放入其他工具、配置或构建产物。 |
| 官方双模式缺一轮／扩展来源或接线不符；重复doctest身份或冻结原始XPASS变化 | 拒绝；不能折叠次数、缺失节点或让新XPASS借原版例外进入。 |
| 额外C实现缺失／链接／越界，原生模块实为Python文件，离线库跨目录或SHA不符 | 拒绝；只允许固定构建控制、真实本次扩展及精确只读库清单。 |
| Pendulum固定时区别名变化、内部目标缺失或沿链接越界 | 拒绝；只在私有测试树恢复已核相对链接，正式快照不创建链接。 |
| 大集合子项缺失、摘要／数量／重复次数／结果不符，完整私有见证或控制器被改写 | 拒绝；不得用摘要表示规避全量检查或提高JSON／日志上限。 |
| Dateutil已核CRLF检出／未知修改或链接 | 前者只在交付副本恢复已核blob，后者拒绝且预检失败不写任何文件；不能通用换行归一化或改上游属性。 |
| 评审实际模型不一致／格式或身份错误 | 评审error，最多一次错误重评，不算业务失败；合法uncertain直接blocked。 |
| 次数或累计预算先到上限 | exhausted／最终failed或评测blocked，独立任务继续，真实后继依赖受阻。 |
| 停止、旧generation、非最新作业迟到结果 | 留历史不接受；认证／真正严格清理失败沿原强门禁阻断批次。 |
| artifact跨实例、非清单path、对象摘要不符 | 拒绝读取或接受，不回退到当前目录；预览最多65536字节。 |

### 5. Scenarios and Examples

- 正常：创建 `{"account_id":1,"project_keys":["python-frontmatter"],"scenario_entries":{"python-frontmatter":{"FM-S02":"diagnose_only"}}}`，服务端生成policy3和600秒默认；FM-S02按diagnose_only入口选择任务，其余场景使用默认入口。正确无BUG／信息不足／方案可通过而不增加代码checkpoint。
- 恢复：前两任务passed、第三任务半途timeout时，旧Run保持timeout，新Run复用第三任务session与半成品，消耗原剩余任务预算；若回答已封存则只续原验收，不新建一次业务询问。
- 串行正常：1536m RAM＋2048m额外swap的新登录保存同环境；network256m／sender128m保持，固定CLI为Memory1152m／MemorySwap3200m。停止CLI后评审使用1152m／1152m，评审停净后恢复原CLI；旧预留CLI640m仍保持原限制。
- 错误用法：只在画像检查前看一次交接标记，随后无锁调用探针和claim，评审可插入停机产生Docker409。正确处理：状态检查、画像exec及认领共同持环境锁，忙碌沿RuntimeBusy重排队；不要靠吞掉409掩盖竞争。
- 代码依赖边界：A接受为作业10、B接受为作业11；以后另一作业把源码回退成A相同字节，不能因此声称B与该回退分支有共同接受父链。使用parent_code_job_id逐作业追溯，无共同链则受阻。
- 错误用法：配置execution_model为空便让评审使用当前全局默认，或给review另开供应商调用；正确做法是沿原Scheduler，冻结候选实际message.model并在review原生日志再次核对。
- 错误用法：CLI success、问答passed或批次completed都算代码成功；正确做法是分别显示执行、任务、代码接受及收口分布。固定测试／模拟CLI通过不计真实模型完成数。
- 正常与边界：TinyDB 的两个修改位于不同场景，分别从原版开始；Jinja M02 声明本场景 M01 的 code 依赖，必须承接真实已接受作业。37 个唯一任务的默认与分支试跑可形成66条路径、10次接受，仍只计37任务与6个唯一修改目标。
- 错误用法：把 `src/jinja2` 当模块名或使用已安装的 Jinja 代替候选。正确配置模块 `jinja2` 与相对导入根 `src`，并以实际 `__file__` 和完整节点合同核对；只读咨询没有候选文件时，移除不适用的候选证据 flag，保留可由公开资料支持的规则。
- 正常与边界：第二批50唯一任务形成114路径／16次接受，仍只计8唯一修改；八修改从各场景原版独立开始，只有TK-P01真实消费TK-D02的answer。四仓D01按实际请求披露，材料不足合法结案；不能把澄清或分支另计任务。
- 错误用法：Tenacity的200汇总当200主节点，或source收账三重叠直接当三个holder。正确做法是185主项＋15真实子项分别核合同，并按实际工作、严格清理和门禁证据说明并发口径及事件留存限制。
- 正常与边界：第一阶段30仓新增244唯一任务，其中9修改；15批mock会重复覆盖入口与分支，重复路径和代码接受次数不增加任务数。完整Git／Docker导出11374文件一致，原3069文件字节及执行位保持；证据见本阶段`research/delivery-first-thirty.json`，不代表真实模型或生产上线。
- 正常与边界：第二阶段30仓新增192唯一任务、8修改，15批mock覆盖562路径／22次接受，仍只计192任务／8唯一修改。完整原生98,924主执行分别为98,459通过、400 skip、64 xfail及1原始XPASS，doctest已含、subtest和收集skip另列。正式22,623文件在Git导出沿生产恢复后与Docker COPY一致，旧11,373文件保持；原始Git检出两份Dateutil CRLF差异明确记录，不代表真实模型或部署完成。
- 正常与边界：第三阶段30仓新增183唯一任务、3修改，15组mock为567路径，其中18条是既有Arrow控制重跑，新增任务路径549条；9次代码接受仍只计3个修改目标。完整原生85820主项为77533通过、6537原skip、1750原xfail，24183子项另列。32188文件经同生产恢复及Docker COPY核字节／权限一致，旧22622文件保持；8960项页面检查和494截图只证明本地模拟机制。
- 错误用法：把SQLGlot的摘要头三个字段当成三个子项，或删除重复context压缩合同。正确做法：1500主项与21780子项分别核实，完整原始观察私有归档，按固定规则对全部记录计算SHA；三组产品链真实回归均须匹配同一合同。
- 错误用法：Dpath以unittest发现得到少量类用例便报完整通过，或将PETL的12个收集skip混入923主项。正确做法是实际nose2完整79项；PETL分别记录923主项与12收集skip，JUnit为935元素。数值只适用于冻结提交与当前环境。

### 6. Tests Required

- 内容／历史／DTO：`test_project_scenario_content.py` 覆盖可变任务、非紧邻DAG、入口可达、隐藏投影、wheel损坏／链接、注册复开摘要、坏catalog历史可读、新600／旧1800默认及显式值／非法null；旧schema夹具回归保留。
- 语言修正：穷举正式首问、分支、材料说明、rubric 与运行时提示，核对英文语义及原授权／验收约束；比较修正前后的中文 `summary(include_steps=True)` 完全相等，新旧内容分别 install／复开仍按各自摘要读取。seed、固定业务输入、原生检查和 wheel 字节保持不变；Unicode 测试夹具与证据原文不作为必须翻译的正式指令。
- 状态／恢复／父链：`test_project_scenarios.py` 覆盖实际消费认领、澄清不加attempt、3次上限、工作高水位／崩溃预留、review三层预算、候选与review严格释放、完整输出quota／重启只续验收、迟到结果、文件交付进review包、局部轮换／分支激活、代码依赖恢复与不兼容／相同字节回退分支、实际模型漂移不扣业务修正。
- 协议／用量／私有运行：`test_project_evaluation.py` 覆盖严格单JSON／错误身份／重复项／未知证据／程序失败不能被pass覆盖、合法uncertain、显式candidate证据许可及缓存字段去重／未知；`test_project_review_runtime.py` 覆盖owner刷新身份、创建／停净／缺失／孤儿、清理失败保留holder及资源份额；`test_project_native_verifier.py` 覆盖准备阶段error、业务exit80为failed、清理前不放slot、合法等价程序提取。
- 串行回归：`test_project_review_runtime.py` 核普通／旧布局不改限额、停止／恢复／退租失败、缺记录及错误代次、同账号竞争与不同账号独立；`test_review_cannot_stop_cli_between_profile_check_and_claim` 固定检查窗口交错，旧实现409、修复后竞争者RuntimeBusy且安装不占环境锁。`test_project_scenarios.py` 核跨活动批次优先及paused／旧代排除。
- 实际Docker：`run_local_verification.py --manifest <隔离验证清单> --project-scenarios-only --scenario-capacity 1 --scenario-failures` 与容量2的 `--scenario-browser` 核新登录同环境、三阶段预算、无候选／评审重叠、私有挂载及原API流。`--scenario-recovery-only` 核真实画像探针与认领竞争、running/exited/missing恢复及缺交接记录阻断；real_model_calls=0，真实OAuth／模型闭环留到部署后独立验收。
- 原生内容：`python3 scripts/validate-project-library.py` 仅静态摘要／当前100-426-726；`scripts/validate-project-scenarios.py --project <key> --task <key> --image <隔离账号镜像>` 真实业务，按需 `--candidate/--answer/--entry/--branch/--expect failed`；`--regression-only` 或 `--with-regression` 使用独立回归资源。保留适用工程目标的原版失败／参考通过／错误候选拒绝、原生完整集合与skip/xfail证据，不用宿主旧基线替代。
- 套件适配：`test_project_native_regression.NativeRegressionTests` 断言 src 叠加恢复原测试／配置、新 pytest hook 拒绝、旧默认不变、父链接与非法路径／模块拒绝、安装库错导入拒绝。目标镜像实际冻结并执行全部节点，再对每个参考候选跑完整适用回归；首批新增原版集合为228／911／81，数字是首批实测记录，不作为后续套件的通用硬编码。
- 第二批适配：同测试类核dotenv受控src／0755入口与退出清理、拒覆盖／系统venv；子测试保留重复context和失败、未知父节点／非call／未序列化值拒绝。当前镜像四仓完整集合为288、1203、1513（1497通过／16冻结skip）、185主项＋15子项，逐参考完整核对；数值是实测，不能硬抄为未来版本通用分母。Git／Docker导出另核来源全集／双SHA、原执行位和link blob表示，私有mount比较核host路径双向重叠。
- 第一阶段适配：同测试类31项覆盖单文件、包内冻结测试、真实unittest／nose2、重复／跳过／失败子项、补充doctest、动态文档描述符、收集skip、离线工具及元数据清理／拒绝边界。当时136项`test_project_*.py`与28项`deploy/v3/test_manage.py`通过；后者核真实上游夹具及未知文件／改字节／链接拒绝。逐仓30原生合同、268业务／回归收据和15批实际产品链审计独立保存；不把本地单测替代镜像内完整原生与业务验收。
- 第二阶段适配：当前原生适配39项、`test_project_*.py`144项、部署30项分别通过。核官方C／Python模式、参数身份、元数据顺序／命令绑定与清理、目录收集skip、重复doctest和唯一原版XPASS拒绝边界；部署核公开.env精确列表及已核CRLF恢复、幂等、模式不变、未知修改／父链接拒绝和预检不部分写入。三十仓204业务／候选路径与15批产品链独立保存；Git证据明确恢复前后口径，沿同生产函数后再核完整Docker交付。
- 第三阶段适配：同类48项包含候选C源码、只读docstring、真实扩展后缀、受控私有链接、库目录绑定、进程池默认值／恢复和大集合完整性拒绝边界；153项项目单测（含该48项）、30项部署测试及最终目录单项回归分别留证。六项审计适配测试基于真实SQLGlot产品结果，拒绝错误数量／SHA／匹配证明、原件／控制器篡改和链接，并核冻结输入文件全集及字节不被写入。完整30仓主集合、170业务控制和15组真实产品链原件独立保存，不以单测代替原生或产品验收。
- 内容评审协议：逐任务及必要披露／无材料路径构造真实 `review_package` 并执行 `parse_review`，核证据标识与候选文件存在性；隐藏具体事实只有实际消费后可用于相应结论。模拟对账同时统计唯一码、路径、披露消费、业务尝试和接受父链，不能把分支或补充材料当作独立任务。
- Git 交付：`git check-attr text`核对冻结数据`unset`、普通代码保持原规则；`git check-ignore`核精确上游例外与本地工具文件仍忽略。被通用规则忽略的其他上游原件，仅在固定Git来源、逐文件SHA／执行位证明后列出精确force-add路径，不宽泛放开目录。用`git checkout-index`导出拟提交内容并按上文同生产函数精确恢复，分别留存恢复前后事实；核文件全集、逐文件字节／执行位及catalog摘要，再沿正式快照过滤器与Docker忽略文件实际COPY核相同集合；工作区摘要不能替代导出证据。
- 真实调度与UI：`deploy/v3/run_local_verification.py --manifest <隔离清单> --project-scenarios-only --scenario-capacity 1`，另测容量2；需要UI与失败恢复时加现有 `--scenario-browser`／`--scenario-failures`。核原Scheduler／driver／SQLite、holder容量、私有挂载与AT-only、超时半成品、仅续验收及页面状态／预算／用量对账；模拟CLI证据明确real_model_calls=0。旧project-iterations／project-scheduling、quota／window及普通题库适用回归继续保留。


## Scenario: 真实 GitHub 项目逐仓研究与百项目扩展 SOP

### 1. Scope / Trigger

- 选项目、研究 GitHub 仓库、编写场景与任务、扩充／替换项目库时适用。历史 100×20 工程路线研究作为来源保留；当前内容池方向为约 100 项目、600～800 场景／2,000 独立任务，每项目数量由真实场景决定，旧生成内容保持退役。
- 本节定义研究与准入流程；legacy `app.py` 协议与新场景原生适配分别按前述版本契约执行。正式接入以逐仓真实准入与当前目录为准，历史研究完成、本地内容可用、模型完成及生产上线分别记录。
- 研究可以复用记录模板与取证工具；源码分析、改进需求和验收目标必须逐仓形成。一个仓库、它的 fork、不同目录副本或改名版本不能计为多个独立项目。

### 2. Signatures

- legacy 入口为 `ProjectVerifier.verify(candidate, cases, timeout=30)`；内容 schema 2 使用 `verify_native(...)` 和场景 manifest。研究文档不直接当作可执行内容；新内容按实际就绪项目加载，不继承 legacy 100／20 的最小数量门槛。
- 单仓研究报告：`research/github-projects/<slug>.md`；二十步路线：`research/github-projects/<slug>-roadmap-20.md`。slug 冲突时包含 owner，不复用不同仓库的报告。
- 原始证据保存于项目外或被忽略的本地证据目录；报告必须给出实际位置和可重跑命令。记录完整上游提交，例如 `git -C <checkout> rev-parse HEAD`，不能仅记录 branch/tag。日志和依赖环境不混入待运行的源码快照。
- 下述研究记录不能替代可执行 manifest、离线环境与独立验收；接入契约见前述内容 schema 2／policy 3。

### 3. Contracts

**每仓固定流程**：

1. **核对来源**：访问官方仓库，确认用途、许可证、上游 URL 和实际存在的提交。保留许可证及必要的归属信息；无法确认可复用条件时暂缓准入。不能只凭仓库名、星数或搜索摘要入库。
2. **检出并读源码**：固定完整 commit，记录真实文件数、源码规模、模块职责和主要入口，读取相关类／方法定义。不得把原工程改写为几十行同构 app.py，再称为真实项目。
3. **验证轻量程度**：在隔离环境安装实际依赖并运行原生入口。记录 Python／Node 等运行版本、依赖锁定依据、系统包、必需服务、安装耗时、环境大小、测试耗时及可取得的内存指标。轻量由实际运行成本判断；需要云凭据、额外服务或较高资源的项目说明限制，不能隐藏成本。
4. **建立原生基线**：优先运行上游适用测试并执行至少一个真实使用场景。记录命令、通过／失败／跳过数、跳过原因、警告和资源配置；未跑的检查明确保留为未验证。依赖缺失不能等同于产品缺陷，部分测试通过不能冒充全套通过。
5. **发现真实改进**：结合上游 issue、文档承诺、实际使用路径和源码缺口。缺陷要在固定提交上复现；新增能力要确认公开入口尚不提供目标能力。记录已有替代方式，区分缺陷、增强提案、已存在功能和待决定的兼容行为。
6. **形成真实场景任务**：逐项记录用户问题、原版现状、交付目标、材料分支、授权范围、兼容边界、正常／反例验收及真实依赖。理解、咨询、诊断、方案和修改按需要选择；任务数可变，不用追问、重试或实现／测试拆分凑数。已有二十项工程路线保留为候选来源，逐项判断是否适合新任务。
7. **独立验收后接入**：控制端持有冻结用例，确认运行时加载候选源码，实际调用原生 API／CLI／UI 并观察文件／数据库等业务效果；累计回归此前已接受能力。依赖提前按固定版本准备，验收期间离线使用；候选不可通过删除自身 tests 或自报成功放行。

**可选私有外部测试的范围**：固定主仓包含不可取得的可选私有测试Gitlink时，先核原生loader是否条件加载，并保存父提交、子模块路径／提交、不可取得证据及完整公开主仓。只有用户明确确认以公开主仓为本轮交付范围后，才按该范围建立准入；私有内容、许可及测试必须明确未验证，不计通过，不修改原loader、设置跳过开关或替换固定项目。可取得的公共测试子模块仍完整导出；不能把这一例外推广到必要源码、许可或测试缺失。

**步骤计数**：一个步骤是一次完整用户可见改进，包含实现、测试、文档及失败修复。同一缺陷的测试矩阵、改代码／写测试／更新文档、失败重试不拆成多个步骤。相关症状可合并，例如 sqlite-utils 两种部分 upsert 问题归为一个保留省略字段的交付。工程修改按接受作业保留检查点；问答通过只记任务结果。只记录真实 answer／code 依赖，不为数量目标强造依赖。

**进度统计**：历史 100×20 工程研究保留其原完成口径。当前新增内容分别统计来源核对、原生基线、场景／任务定义、冻结验收与平台接入；就绪还须固定材料、离线环境及独立适配实际通过，不设每仓 20 任务门槛。生成名称或 clone 数量不等于完成内容；研究完成、验收可用、模型完成和生产部署分别报告。

**旧内容退出**：正式源码中的 `project_library/projects/project-001` 至 `project-100` 及旧目录清单退役，移除正式批量生成入口；不得改名、换 README 或增加 GitHub URL 后继续充当真实项目。为调度器回归需要的合成内容只能在隔离测试目录临时构造，明确标记测试用途，不作为正式 catalog 或交付统计。已冻结的发布目录、实例工作目录、历史 DB 和成果不因源码清理被批量删除。源码清理与实际部署分别报告，不能以本地删除推断线上已清除。

**空库与接入**：真实内容尚未就绪时，不自动重新生成旧项目补足 100。内容 schema 2 允许部分就绪项目接入；空库或不合法内容拒绝新准入，历史 reader 与当前 catalog 分离，旧题库保留原入口。保留已经完成的真实项目研究；原生入口、离线依赖、独立验收和预算适配完成之前，不把它包装成 legacy app.py 协议接入。

### 4. Validation & Error Matrix

| 条件 | 处理与计数 |
| --- | --- |
| 只有名称／URL，未读源码或未检出固定 commit | 保持候选，不计研究完成 |
| 许可证、必要服务或依赖条件尚未查清 | 记录原因，暂缓准入 |
| issue 在冻结提交上无法复现，或目标能力已存在 | 重新分析／移除该步骤，不计有效缺陷 |
| 新接口仅检查到缺失，尚未实现 | 记录增强提案，不能声称修复验收通过 |
| 基线失败、系统依赖缺失、网络不可达或测试被跳过 | 保存实际结果和原因，不伪报通过；未解决的适用基线失败不计研究完成 |
| 场景目标／独立验收尚不明确 | 继续研究，不拆追问、测试或重试凑任务数 |
| 100 条模板或同源副本 | 不计为 100 个真实项目 |
| 原生基线通过，但未接入适用原生适配器 | 研究与平台接入分别记录，不冒充可运行内容 |
| 删除旧源码目录后，当前运行实现拒绝空库 | 明确报告项目入口暂不可用，不恢复旧生成内容兜底 |
| 清理命令指向已冻结发布、实例成果、生产 DB 或未知目录 | 停止扩大范围，按实际环境与归属另行处理 |

### 5. Scenarios and Examples

- 正常：`simonw/sqlite-utils` 固定 `9c66bafa52ae23d40499c74b0db3b635bcddb876`，原版全套测试 1,497 通过、16 跳过；相关原生测试在正式账号镜像隔离运行 75 项通过。二十步路线含9步已复现问题修复和11步功能增强提案，研究本身不等于实施；第二批现已另行接入本仓4场景／13任务和两个独立修改验收，不表示原二十步已全部实施。
- 证据入口：[单仓审查](../../../../research/github-projects/sqlite-utils.md)、[二十步路线](../../../../research/github-projects/sqlite-utils-roadmap-20.md)。原始 JSON／脚本位置以报告为准，不能将本地证据目录可用性当作跨机器保证。
- 边界：前 2 步闭环通过只证明这 2 步完成；后 18 步仍按各自状态记录。一个适用基线通过、20 步研究齐备但未接入的项目，只增加研究完成数。
- 错误用法：批量生成 100 个 44 行 app.py，给每项拼接 20 个通用操作，再声称真实 GitHub 项目库扩充完成。正确做法：逐仓读取真实代码、执行原生基线、核实需求和路线；未满足条件的保持候选状态。
- 错误用法：删掉旧正式目录后，为使数量检查／测试通过重新写回同一批合成项目。正确做法：正式目录只接入已就绪真实内容，调度测试显式使用临时合成夹具；历史成果单独保留。

### 6. Tests Required

- 单仓审查：核对仓库归属、完整 commit、许可证、源码规模、真实入口、依赖版本与测试日志；至少一个原生使用场景实际运行，报告中的通过／失败／跳过数与原始输出相符。
- 场景审查：可变任务数量、稳定 ID、同场景真实 DAG、入口／分支可达、材料披露和分类验收均合法；缺陷原版复现，增强核对实际缺口，不重复计算追问或重试。历史二十项文档单独保留其数量审计。
- 独立验收：正例、反例、基线和此前已接受能力均实际运行；核对候选加载路径、真实业务副作用、超时、依赖不可用及输出边界，禁止候选修改冻结验收。完整原生集合和单步集合的资源预算分别实测。
- 进度对账：来源不同的仓库去重；候选、研究完成、验收就绪、模型完成及生产发布各自统计。未解决的适用基线失败或未完整定义的步骤不得进入研究完成计数。
- 退役回归：正式库无旧 100 项和正式生成入口；合成夹具只在测试临时目录出现；旧库不能被默默重建。调度／验证测试改用显式夹具，保留目录接续、检查点、停止和并发回归；确认源码清理未修改历史发布与实例数据。

## Scenario: 内容 schema 3 的完整开发周期与动态需求方配置

### 1. Scope / Trigger

- 修改 `project_dialogue.py`、`project_development.py`、`project_requester_settings.py`、完整任务恢复／验收、`#projects` 配置表单或 schema 3 内容时适用。
- 一个需求或 BUG 对应一个完整任务；源码调查、追问、方案确认、实施、交付和修复属于同一任务、同一开发者会话与工作区。普通交流不启动独立评分。
- 原账号身份、运行时段、额度、执行许可、严格释放和私有最终评审继续遵守既有账号契约。

### 2. Signatures

```python
ProjectLibrary(root, minimum_projects=100, minimum_steps=20, catalog_name='catalog.json')
ProjectDialogueClient(base_url, api_key, model, fallback_model='', *, timeout=30,
                      opener=None, additional_models=None, revision='environment')
ProjectDialogueClient.generate(context, preferred_model=None, timeout_sec=None)
ProjectRequesterSettings(path, environment=None)
ProjectRequesterSettings.public()
ProjectRequesterSettings.save(base_url, models, api_key=None, *, compaction_threshold_tokens=None)
ProjectRequesterSettings.reset()
```

- `GET /api/settings/project-requester`：读取脱敏配置。
- `PUT /api/settings/project-requester`：`{base_url: string, models: string[], api_key?: string|null, compaction_threshold_tokens?: integer|null}`；未知字段拒绝，Pi 阈值见下文 token 摘要契约。
- `DELETE /api/settings/project-requester`：清除页面覆盖并恢复环境初始值。
- 响应字段为 `base_url`、`models`、`api_key_configured`、`source`（`page/environment/invalid`）、`revision`、`ready`、`error`、`compaction_threshold_tokens`；不返回 `api_key`。
- `project_dialogue_jobs` 以 `evaluation_job_id UNIQUE` 绑定冻结回答，保存 `task_id/generation/status/phase/request_json/result_json/attempts_json/model/work_sec/reserved_sec/recoveries/retry_at/error` 及时间；不新增需求方 CLI 作业角色。

### 3. Contracts

**配置与请求**：

- 页面仅管理一个 HTTPS Base URL 和按优先级排列的 1～8 个不重复模型。首个主用，后续按序降级。模型使用 `MODEL_NAME` 校验；地址不含认证、query 或 fragment；地址和模型名不得混入密钥。
- 环境初始值使用 `PROJECT_REQUESTER_BASE_URL`、`PROJECT_REQUESTER_API_KEY`、`PROJECT_REQUESTER_MODEL`、`PROJECT_REQUESTER_FALLBACK_MODEL`。页面覆盖原子保存到 `BENCH_DATA/settings/project-requester.json`，文件 0600、创建的父目录 0700；保存密钥留空时沿用服务端当前值。保存不发出连通请求，`ready` 只表示配置语法完整。
- 保存成功后替换管理器的后续请求客户端；在途客户端保留开始时的地址、模型与配置版本，已生成有效消息继续复用。配置版本变化后重新按新列表选模；同一版本内当前任务沿用已选模型，避免每轮重试已耗尽的主模型。
- `POST <base_url>/chat/completions` 使用 Bearer、非流式 `messages` 和 `max_tokens=1024`；禁止自动重定向。一次生成对每个模型最多尝试一次；单模型默认网络超时 30 秒，控制端共用最多 60 秒预留及任务剩余预算。
- 402／明确额度错误、429、500／502／503／504 和传输故障可有限降级；认证、参数和无效回复错误不通过换模型掩盖。主备均失败有限等待恢复；未知在途结果保留预留并阻塞盲重发。
- 严格 JSON 只有 `action` 和 `message`；动作只允许 `reply/implement/verify`，前两种消息非空。重复字段、截断、工具调用、拒绝、额外评分字段和密钥反射均拒绝。
- 请求只含任务、可披露业务材料、真实对话和已确认方案，业务上下文不超过 512 KiB、响应不超过 64 KiB；私有 rubric、验收源码、参考补丁和凭据不进入请求。调用及配置版本、服务地址、请求／返回模型、实际 usage 分别留证，缺失统计保持未知。

**原会话与验收**：

- 先凭原生父链确认输入／回答并严格释放执行，再由外部需求方推进。有效结果先保存后应用；同一冻结回答重放不重调模型、不重复投递。
- 仅方案确认后的实施／返工阶段允许 `verify`。最终交付依次核授权范围、独立程序事实、冻结回归和必要交付审查；程序未通过不能接受代码，模型不能自行声明任务完成。
- 失败反馈提供可公开的位置与实际差异；大型回归保留失败事实而非完整收集清单，并按 UTF-8 字节有界。真实代码修复最多两次，同版本语义异议只复核一次；确定程序失败必须修复，存疑结论保留交付待处理。
- 超时仅结束执行片段；Run 保留 timeout，原会话、方案及半成品待续做。任务工作预算累计开发者、最终评审和需求方时间及未决预留；普通交流和基础设施切片不计业务修复。
- 同账号可执行的续做优先于新需求；服务等待不占 Claude 执行名额。停止、身份变化、会话／工作区缺失、消费不明、预算耗尽和严格释放失败均不能被自动恢复绕过。
- 已生成未投递复用原消息；已投递未确认先核原生消费；已消费未回复续原会话；交付待验收继续原冻结版本；程序验证已完成但结果未收口复用原验证事实。

**内容与页面**：

- schema 3 每场景恰好一项 `kind=modify`、`development_cycle=feature|bug` 的任务，具有独立原生验收，不携带旧短题 `max_turns`。`owner_materials` 只引用 `disclosure/` 中的业务材料。
- 目录可用 `project_manifest=development.json` 选择新定义，保留原 `project.json` 与 `catalog-v37.json`；冻结历史不迁移。`admission` 的 ready 集合必须精确等于可执行项目集合，blocked 必须有原因。
- 当前重审口径为 100 项目、30 就绪项目／36 完整任务、70 待准入；旧 426 场景／726 短任务和研究提案单列。生成目录不能替代准入证明，激活须由 `build-project-development-content.py --activate --validation-report <回执>` 核全部任务覆盖与内容摘要。
- 页面按完整交付计完成数，轮次、业务修复、异议复核及服务恢复分别展示；连续对话按需读取。开发者、需求方、最终评审用量单列，缓存命中以真实服务证据为准。
- 局部 `<pasted_content>` 包装只在同 ID 单层标签与已知边界换行移除后，能精确还原原输入时接受；额外正文、不同 ID 和嵌套／多重包装拒绝。

### 4. Validation & Error Matrix

| 条件 | 处理 |
| --- | --- |
| HTTP 地址、重复或超过 8 个模型、密钥混入地址／模型 | 配置 PUT 400，保持原配置和客户端 |
| 配置字段类型错误／未知字段 | 422，固定错误不回显密钥输入 |
| 未登录／无内部服务凭据 | 沿用管理鉴权拒绝读取与写入 |
| 配置保存失败 | 500，旧客户端及私有配置继续生效 |
| 页面文件损坏 | `ready=false/source=invalid`，拒绝盲用环境供应商；可完整重填或恢复环境 |
| 新完整任务尚未配置客户端 | 拒绝新批次，历史 reader 保持可用 |
| 配置在请求中修改 | 保存原结果及来源，下一请求采用新版本 |
| 未确认方案即 verify | 阻塞提前验收，保留会话 |
| 明确程序失败或复核次数耗尽 | 不接受交付，具体反馈或保留阻塞原因 |
| 验证已完成／收口重复到达 | 复用原事实，只接受一次任务完成 |

### 5. Scenarios and Examples

- 正常：页面填写 `https://ai.flower-cli.com/v1`，模型按 `gemini-3-flash-agent`、`deepseek-flash` 排列。主模型额度不足后转备用，方案确认和实施都在开发者原会话进行。
- 边界：管理员改变地址和模型顺序，密钥留空；已生成追问仍发送原内容，之后的需求方请求使用新版本，已运行客户端保留原来源。
- 错误：普通问答每轮都要求 pass；或将 slice timeout 当作任务结束并重建 seed。正确：普通回复直接推进，超时严格释放后恢复原会话与工作区，共用累计预算。
- 错误：只凭语义 pass 覆盖程序失败、将问题改名补齐百项目数、或因结果未知盲重发 API。正确：保留独立事实、逐仓准入和未决预留，分别处理真实失败与基础设施恢复。

### 6. Tests Required

- `test_project_dialogue`：请求格式、严格动作、额度／限流／5xx／传输降级、认证不降级、总时限、重复字段与密钥反射；另核 `_NoRedirect` 是生产 opener 的实际处理器。
- `test_project_requester_settings`：私有权限、重载、空密钥沿用、恢复环境、多个模型顺序、在途客户端保持、保存失败原子性、API 鉴权与 DTO 错误脱敏。
- `test_project_development`：十轮普通交流零评审、确认方案、具体失败修复、有限异议、超时／暂停／重启／停止竞争、配置变化与缓存消息、续做优先、预算和接受幂等。
- `validate-development-content.py`：逐任务核原版失败、参考通过、授权范围、冻结回归；双试点另拒绝错误候选。来源、许可证、离线制品与交付副本摘要一致。
- `verify-project-development-pilots.py --browser`：合成开发者／语义评审、本机 HTTPS 需求方、真实 SQLite／原生交接／Docker 原生验收；Chrome 双主题与 390／1280 宽度核配置保存、三模型降级、新 Bearer、连续对话及 API 对账。
- 真实供应商最小连通、真实模型完整业务、模拟机制及生产部署分别留证；未实测的模型质量、费用与缓存收益不报通过。

## Scenario: Pi 项目与工程养号每次指挥只处理一个目标

### 1. Scope / Trigger

- 修改 `ProjectsService` 的目标创建、交付收口或 `images/pi-agent/host.mjs` 的工具结果与循环结束时适用。
- 一次指挥按账号、空间和控制者 `generation` 区分；养号的 `cycle_no` 是完整工程池轮次，两者不能混用。

### 2. Signatures

```python
ProjectsService._check_round_work(account_id: int, generation: int, work: dict | None) -> None
ProjectsService.tool(account_id, generation, name, args, call_id, stop=None) -> dict
# project_submit 完整通过并成功释放原执行后的工具结果：
{"submission_id": "...", "status": "passed", "round_complete": True}
```

- Pi 沿现有 JSONL `tool_result.result` 接收该字段；只在 `project_submit`、`status='passed'`、`round_complete === true` 同时成立时采用 SDK `AgentToolResult.terminate`。
- 不新增 HTTP 请求参数、环境键或数据库列。`projects_*` 与 `warmup_projects_*` 分别保存各自目标、代次及通过事实。

### 3. Contracts

- 每次指挥最多绑定一个工程目标；已有未完成工作优先恢复。后端按该账号及代次查询持久工作，已结束或已绑定其他工作时拒绝创建第二项。入口及选材后发布前均在服务锁内核对，不能仅依赖模型指南。
- 完整交付验收通过、通过事实保存且原 Claude 执行成功释放后，才返回布尔完成标志。失败返工仍属同一目标；超时、额度等待和重启按原门禁续原 work、工作区、会话与累计耗时，不重建 seed。
- Pi 先让 SDK 保存真实工具结果，再结束本次循环。混合工具批次中完成后的工具不再交给控制端；`prepareNextTurn` 阻止后续推理。新进程的结束标志重新初始化，旧会话中的完成字段不能提前终止下一次指挥。
- 可信目标完成后无需额外生成摘要或回复；此次收尾停止额外压缩／推理。同目标的 token 摘要策略见下文，模型重试和降级规则保持。SDK 因混合批次收尾生成的零用量本地 aborted 消息不计入上游调用。
- 正常收尾复用原计划排期；关闭计划不自动重启，开启时遵守各自固定或随机间隔。人工暂停、取消、控制代次变化和共享账号占用继续优先，异步收尾后须再次核取消状态。
- 两种迭代共用该边界。养号必须全部工程目标独立通过后才在后续合法认领时清理并重开工程池，不能在完成单目标时清零。项目迭代不自动重开工程池。
- 发布须同时更新共享后端和 Pi 入口，重载后保留原会话、通过事实及各空间计划；不能只更新指南或只更新单侧运行文件。

### 4. Validation & Error Matrix

| 条件 | 处理 |
| --- | --- |
| 本轮首目标已通过或停止，又请求新目标 | `status='rejected'`，不新增工作或启动 Claude |
| 并发首次选择不同目标 | 发布前复查，只允许一个工作落库并启动 |
| 验收失败、基础设施异常或执行收口失败 | 不发完成标志，按原返工／阻塞规则保留现场 |
| 其他工具携带完成字段，或字段是数字等非布尔值 | 不触发 Pi 单目标收尾 |
| 完成时人工暂停或取消 | 不重开计划，不把迟到结果覆盖新代次状态 |
| 下一次合法启动 | 可选择下一目标；未完成工作则只恢复原目标 |

### 5. Scenarios and Examples

- 正常：目标 A 通过后结束本次指挥；原计划间隔到期且门禁放行，再开始目标 B。
- 边界：目标 A 多次片段超时，下一次指挥仍使用同一 work/session，累计耗时保留；单轮时限沿用当前配置，本契约不另设累计预算策略。
- 错误：修改提示词后仍允许本轮 `claude_start` 创建 B，或为了结束 Pi 丢掉 A 的真实工具结果。正确：后端限制目标，并在 SDK 保存通过结果后结束循环。
- 错误：把“单目标已完成”当成养号全部工程已完成。正确：`cycle_no` 仅在全部独立通过后的后续认领推进。

### 6. Tests Required

- `test_projects_single_objective`：两空间第二目标拦截、并发发布、失败返工、超时保留两个会话、人工暂停竞争、执行收口失败，以及养号重开后首目标仍单独收尾。
- `test_projects_pi_round`：真实 Python→Node→SDK 管道中，通过结果持久化、父进程得到 settled、上游请求恰好一次。
- Pi `host.test.mjs`：单工具及混合批次、完成字段严格校验、停止后的工具不执行、原会话重开不重放工具、取消优先和本地空用量不冒充上游调用。
- 依赖、调度、命名空间和工程池回归须按真实跨轮代次构造；不能继续用同一代次连续完成多个目标的旧夹具来绕过新边界。

## Scenario: Pi 按工程目标隔离上下文及可配置 token 摘要

### 1. Scope / Trigger

- 修改 Pi 会话恢复、工具循环、模型设置或目标材料读取时适用；项目与工程养号共用此契约。
- 固定 SDK 0.75.1 的原生压缩未覆盖持续工具循环，且零用量错误尾消息不能代表此前上下文已变小，因此由宿主在安全边界统一判断。

### 2. Signatures

```text
GET/PUT/DELETE /api/settings/project-requester
ProjectRequesterSettings.agent_configuration() -> dict | None
contextTokens(messages, fixedTokens = 0) -> number
freshContext(manager) -> object | null
compactContext(manager, options, summarize, signal) -> Promise<object | null>
account_state({offset?: integer, limit?: integer})
project_read({project_key: string, objective_id?: string, section?: string, offset?: integer, limit?: integer})
```

- Pi 启动配置新增 `context_mode='fresh'|'resume'` 和 `compaction_threshold_tokens`；`options` 包含 `threshold/fixedTokens/force/deadline`。
- `context` 事件仅持久化 `reason`（`new_objective/startup/threshold/overflow`）、非负整数 `before_tokens/after_tokens`（上限 `2**40`）及控制端 `generation`；不保存摘要正文、凭据或私有路径。

### 3. Contracts

- 上下文隔离边界是工程目标：开始新目标采用 fresh，本地追加隔离检查点；已有未完成目标采用 resume，跨控制代次继续原历史。不得在每次模型请求前重建。原始 Pi 文件、Claude 会话、工作区、输入事实和累计耗时留档。
- 压缩阈值默认 `350000`，范围 `10000..900000` 且必须为严格整数。PUT 中省略或 null 沿用当前值，旧私有 schema 1 文件缺字段时补默认；保存仍原子写 0600 文件并更新 revision，读取接口不返回密钥。启动／恢复冻结配置，两空间同时适用；没有新增环境键或数据库列。
- 达到阈值时触发摘要。优先使用最近有效助手的 `input+output+cacheRead+cacheWrite`，再估算后续内容；排除错误／取消及摘要前旧用量。无有效用量则使用 SDK 估算并计入固定指南和工具定义。自定义规划窗口不改变上游真实容量。
- SDK 原生自动压缩关闭。启动／恢复前和工具批次结束检查阈值；工具回执先持久化，再结束 SDK 子循环，在空闲边界摘要并 continue，不重发已确认工具或用户输入。正常正文不做字节硬裁剪，未配对工具及失败助手不进入模型历史。
- 较早正文按至多约 16000 个估算 token 分块，顺序归纳并携带上次摘要；近期完整交互最多保留 `min(12000, threshold/4)` 个估算 token。各片段摘要须非空且估算不超过 8192；取消／原截止时间仍允许，且估算用量确实降低并低于阈值后才追加检查点。异常不发布新检查点，原文保留。
- 摘要和普通推理共享本轮额外尝试上限（至多 8 次）、模型健康状态、同模型重试／降级、服务端等待及原截止时间；真实摘要调用纳入计量。Python 传来的剩余秒数可带小数，宿主须向下取整到整数毫秒后建立截止时间，避免 `AbortSignal.timeout` 拒绝小数或延长原预算。可信目标完成后直接收尾，无额外摘要或推理。
- 当前已知限制：摘要 `stopReason='length'` 仍可能通过非空及长度检查并发布未完成摘要。此行为属于 FBK-001 的保护缺口，不能把现有检查描述为已保证摘要完整结束；不代表磁盘原文已删除。
- 真正 400／413 上下文拒绝最多在强制摘要且确实缩减后续接一次；认证、明确内容拒绝、禁止重试、服务端等待及原预算优先。无法缩减或重复拒绝明确报 `context_limit`，不盲发相同超长请求给其他模型。
- `account_state` 的 offset 默认 0、limit 默认 10 且范围 1..20；三个列表 `available_objectives/waiting_objectives/passed` 同步分页，`objective_page` 给出各自真实总数及公共 next_offset，保留全部未完成目标数量。模型视图去除重复指南，页面完整视图保持。
- `project_read` 默认读取 overview，提供 objective_id 时默认读取 objective，research 读取研究；offset 默认 0、limit 默认 1000 且范围 1..2000，按字符返回 `content/offset/limit/total_chars/next_offset`。原工作继续使用冻结材料，仅提供公开正文，不向模型暴露私有验收。
- 已确认 `context_limit` 可按既有显式启动入口恢复；旧通用错误须先追加绑定原错误的 `operator_diagnosis`，事件键为 `operator-diagnosis:context-limit:event-<原事件ID>`。身份、未知输入、合同及账号门禁仍须满足，不能泛化解锁。
- 镜像必须同时包含 host 与 `context-policy.mjs`，Docker COPY 与上下文白名单成对更新；发布后核对前后端字段和两空间运行版本。

### 4. Validation & Error Matrix

| 条件 | 处理 |
| --- | --- |
| 阈值为 bool／字符串／小数或未知 DTO 字段 | 422；整数越界为 400，均保持原配置 |
| 旧配置缺阈值，或新配置省略该字段 | 分别补 350000 或沿用已保存值；下一次启动／恢复生效 |
| 百万级历史后有零用量 error／aborted | 仍依据此前成功用量，分段摘要后恢复原目标 |
| 摘要抛错、为空、过长、未降低用量或取消／超时 | 不发布新检查点，不继续超长推理；原历史保留 |
| 摘要返回非空但 finish_reason=length | 当前已知保护缺口：仍可能发布并继续，见 FBK-001 |
| 强制摘要后仍收到真实上下文拒绝 | 明确 context_limit，不继续自动重试 |
| 分页参数非法或材料 offset 超出正文 | 工具返回 rejected，不能把截断页当作完整清单 |

### 5. Scenarios and Examples

- 正常：新目标 A 使用 fresh；同一目标的多次模型／工具交互连续保留。累计输入含缓存达到 350000 后摘要，再继续 A；A 通过后结束，下轮 B 再隔离旧上下文。
- 边界：保存 `{"base_url":"https://ai.flower-cli.com/v1","models":["gemini-3-flash-agent"],"compaction_threshold_tokens":450000}`，密钥沿用；下次项目或养号启动均采用 450000，在途执行保留原阈值。
- 错误：每次请求清空历史、按 24 KiB 硬裁剪材料，或只看首 10 个目标就报告全部完成。正确：以工程目标隔离，同目标按 token 摘要，沿 next_offset 读取剩余页。
- 错误：直接重发百万级旧历史，或清空会话解除旧通用错误。正确：分段归纳，并凭绑定原错误的诊断经原门禁显式恢复。

### 6. Tests Required

- `test_project_requester_settings`：默认、旧文件、保存重启、字段省略、严格类型／值域、密钥脱敏及失败原子性；`test_projects_single_objective` 核保存阈值进入两空间启动快照。
- `context-policy.test.mjs`：缓存用量、零用量尾消息、摘要前旧 usage 失效、完整正文分段、近期工具配对、原文留档及失败／取消不发布检查点。
- `host.test.mjs`：350K／自定义阈值、小数剩余预算下实际摘要成功、百万级历史、连续工具流、强制摘要仅一次续接、计量、摘要内容过滤同模型重试后降级及 DeepSeek 关闭思考。
- `test_projects_agent`：目标级 fresh/resume、600 项分页与材料分段还原、公开事件白名单、旧错误诊断及未知输入／身份门禁。
- 摘要 length 的本地真实 SDK 故障注入已复现 FBK-001；未修复前不得将“截断摘要被拒绝”计为已通过断言。
