# 项目迭代模式契约

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

旧 100 个生成项目、生成器和参考运行时保持退役。当前源码 catalog 为内容 schema 2，六个真实项目共 26 场景／57 任务；原生适配与场景执行见后节。legacy 调度回归由 `orchestrator/project_test_content.py` 在临时目录构造夹具；源码变更不代表生产已部署，不删除历史发布及实例成果。

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
- 当前源码内容为 `real-project-scenarios-v3-en`：python-frontmatter 4场景／6任务、pydantic-settings 5／7、Typer 4／7、TinyDB 4／12、Jinja 4／12、schedule 5／13，合计6项目／26场景／57任务，其中48个非工程任务、9个工程任务。线上基线 `ci-39609484070-1` 仍为原3项目／13场景／20任务，本地内容通过不代表已部署。任务类型固定 `understand/consult/diagnose/plan/modify`，不要求每项目20步。内容就绪、本地模拟机制、真实模型完成及生产部署分别计数。

### 2. Signatures

```python
ProjectIterationManager.create_batch(account_id, name, project_keys=None, policy=None, scenario_entries=None)
initialize_scenario_schema(connection) -> None
normalized_scenario_policy(values, project_count, account_limit) -> dict
ProjectVerifier.verify_native(candidate, project_root, specification, environment_root, profile,
                              *, answer='', regression=False) -> dict
ProjectScenarios.finish_captured_quota(run_id) -> bool
observed_model(directory, response, session_id) -> str
_suite_paths(suite: dict) -> tuple[Path, Path]
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

**严格释放与接受**：真实父链／输入消费／source/generation核对后定向冻结、封存回答和候选，并先持久waiting_release与complete决定。driver正常退出，精确来源严格释放后才排机械验收；需要评审时经原Scheduler／normal额度和共享CLI租约创建project_review，候选不持名额等待评审。评审结果封存后也须严格释放，CAS核对父generation／状态、最新作业及未收口执行后才接受或披露／有限修正。重复候选／评审通知重放已落决定，不重复freeze；迟到旧代结果不推进。完整输出遇quota／重启只续验收，不再重问；旧Run终态保留。

**同实际模型评审**：场景冻结原账号身份、CLI版本、effort和配置execution_model（空串也是合法配置快照）。候选封存时从已核对主assistant精确原生位置读取 `message.model`，存evidence `resolved_model`；私有评审用该值作 `CLAUDE_MODEL_OVERRIDE`，评审结果再核实际原生模型完全一致。禁止因CLI默认／全局设置变化静默换模型，也不调用模型清单探测。评审使用独立session／PID／mount／HOME／input／日志，原账号netns、AT-only副本和唯一刷新所有者；候选无法从其共享目录读取隐藏材料。资源从原账号静态预留512MiB单评审池，CPU按CLI／review／network／sender=4／2／1／1分配，CLI／review的PID为384／128、tmpfs各64MiB，额外swap只归固定CLI；旧已创建环境缺匹配layout时明确拒绝并要求空闲重建，不超分账号预算。

评审包冻结完整已消费当前任务对话、回答、rubric、真实源码事实、程序结果及实际交付candidate_files（逐对象摘要核对），总上限512KiB，超限受阻不截断。输出最多64KiB的单JSON，身份字段为 `job_id/task_id/turn_no/response_digest/basis_digest`；decision限disclose/pass/fail/uncertain，逐criterion恰好一次，证据必须在冻结清单且candidate引用获显式许可，反馈限白名单。程序失败不能被语义覆盖；合法uncertain直接受阻，不重抽。modify仅在native及适用regression通过后接受；声明semantic的交付要求还须评审。

原所有者刷新待办位于 `project-review-owner-refresh/<account_id>.json`，绑定 request_id／原身份／environment_id与generation／被拒AT摘要。旧身份、旧环境或原所有者已发布不同且未过期AT的请求不阻新准入；新请求把旧记录归档为superseded并保留previous_status。当前被拒AT的error仍阻断；双参数 `refresh(account, request)` 在原owner锁内重读身份／环境／request_id，迟到写回用request_id CAS，不能刷新或覆盖新请求。私有作业未停净时保留holder及创建意图，未知running孤儿阻止第二评审。

**预算与恢复**：policy3候选 `timeout_sec=600`、`task_budget_sec=1800`；业务首轮加最多2次继续／修正，实际输入消费才扣，正常澄清与额度接续不增业务尝试。`review_timeout_sec=180` 限同一逻辑评审跨Run/source累计；同回答最多首次＋1次错误重评且回答总上限为其2倍；`review_budget_sec=720` 限任务全部回答轮次累计。单次领取三层剩余量最小值，infra恢复对业务任务／冻结回答各最多2次，不重置余额。候选及任务累计、任务review累计公开范围60～86400秒；review单次60～600；实际剩余不足公开最小值也不能向上补发。boot＋monotonic片段启动前预留，退出按真实高水位结算，尾段不明保留预留且受阻，不伪造耗时或清零。token按精确source字节区间、session/message去重，统计complete与任务passed不同。

**原生验证**：`verify_native` 在同批account镜像、UID1000／network none／只读根／无账号凭据内执行；源码、baseline、offline、控制脚本与输入只读，临时运行树隔离。离线准备阶段证明与业务时限分开；环境error只本地有限重试，不投递业务修正。工程回归从固定baseline恢复上游适用集合，核Python／插件／baseline与节点contract，业务通过后真实执行，不只检查声明或退出码0。新原生验证的并发名额覆盖容器清理；清理无法确认时保留阻断记录。内容复制、Docker忽略与源码快照须一致；Typer上游公开.env仅按精确固定路径／摘要保留，不放开其他环境文件。

**原生套件布局与校准**：`SUITES.package` 是可导入模块名，`implementation_dir` 默认按模块点号转路径，`import_root` 默认为 `.`；两路径必须相对、无 `..`，且实现路径等于导入根拼接模块路径。Jinja 固定 `package=jinja2,implementation_dir=src/jinja2,import_root=src`；只叠加实际实现，拒绝实现及父目录链接，恢复 baseline 测试／配置并拒绝新增 pytest 控制声明，实际 import 必须落在受控测试树。新增 TinyDB／Jinja／schedule 套件在目标镜像收集非空、无重复的真实节点并完整执行，冻结 schema／project／baseline_digest／python／plugins／nodes；候选逐节点及结果精确匹配合同。旧三个 suite 保留原硬固定计数和默认布局。新增内容的回归脚本副本与共享可信实现逐 SHA 一致，旧内容私有脚本不原地升级。

**Git 字节保真**：正式 `project_library/**` 和本任务冻结研究证据使用 `-text`，禁止 Git 行尾转换改变已验证摘要。python-frontmatter 固定提交的 `seed/library/AGENTS.md` 按来源文件清单精确保留，忽略例外仅限正式副本与对应研究副本，本地工具 AGENTS.md 仍忽略。提交前从索引导出内容，逐文件核对清单与原始字节，并重新加载 `ProjectLibrary` 比较 catalog 摘要；工作区校验不能替代 Git 导出校验。上游空白、原始帮助输出及统一补丁上下文按原样保存，原创实现仍做空白检查。

### 4. Validation & Error Matrix

| 条件 | 结果与边界 |
| --- | --- |
| 新内容省略预算／显式合法预算 | 依内容选择600等新默认／按原值冻结；不能被DTO旧1800覆盖。bool/string/float/null预算与未知字段拒绝。 |
| 旧内容提交新专用预算或入口字段 | 明确拒绝；旧无schema／policy2语义保留。 |
| 当前catalog损坏，历史release完整 | catalog／新建503，历史批次／回答／文件仍按固定release可读。 |
| 缺依赖、跨场景依赖、环、code引用非modify | 内容准入拒绝；未选分支不计本次必要任务分母。 |
| code依赖无接受作业／父链不一致／交接replacing | 保留现场并受阻，不以当前cwd或相同摘要猜测继承／合并。 |
| 候选完整但未严格释放、评审未释放 | 保持等待，不能接受、重问或开始相冲突执行；容量1也不持候选holder等待评审。 |
| 完整候选／评审输出后quota或重启 | 只续收口与验收，保留Run中断事实，不重复模型输入或计量。 |
| 新source未许可／许可后尾段不明 | 前者有持久证明可结算未投递；后者保留预留并受阻，不盲给新预算。 |
| 原生准备异常／业务断言或已进入业务后的超时 | error／failed，前者本地有限重试，后者可用有限业务修正。 |
| suite 模块／相对路径不匹配、实现或父目录链接、候选错导入安装库 | 拒绝回归；候选源码违规为 failed，不借环境重试接受。 |
| 冻结合同来源不符／Python或插件漂移／空节点或节点结果不符 | 拒绝；环境漂移须重新校准原版，候选不能靠删测试或退出码零通过。 |
| 评审实际模型不一致／格式或身份错误 | 评审error，最多一次错误重评，不算业务失败；合法uncertain直接blocked。 |
| 次数或累计预算先到上限 | exhausted／最终failed或评测blocked，独立任务继续，真实后继依赖受阻。 |
| 停止、旧generation、非最新作业迟到结果 | 留历史不接受；认证／真正严格清理失败沿原强门禁阻断批次。 |
| artifact跨实例、非清单path、对象摘要不符 | 拒绝读取或接受，不回退到当前目录；预览最多65536字节。 |

### 5. Scenarios and Examples

- 正常：创建 `{"account_id":1,"project_keys":["python-frontmatter"],"scenario_entries":{"python-frontmatter":{"FM-S02":"diagnose_only"}}}`，服务端生成policy3和600秒默认；FM-S02按diagnose_only入口选择任务，其余场景使用默认入口。正确无BUG／信息不足／方案可通过而不增加代码checkpoint。
- 恢复：前两任务passed、第三任务半途timeout时，旧Run保持timeout，新Run复用第三任务session与半成品，消耗原剩余任务预算；若回答已封存则只续原验收，不新建一次业务询问。
- 代码依赖边界：A接受为作业10、B接受为作业11；以后另一作业把源码回退成A相同字节，不能因此声称B与该回退分支有共同接受父链。使用parent_code_job_id逐作业追溯，无共同链则受阻。
- 错误用法：配置execution_model为空便让评审使用当前全局默认，或给review另开供应商调用；正确做法是沿原Scheduler，冻结候选实际message.model并在review原生日志再次核对。
- 错误用法：CLI success、问答passed或批次completed都算代码成功；正确做法是分别显示执行、任务、代码接受及收口分布。固定测试／模拟CLI通过不计真实模型完成数。
- 正常与边界：TinyDB 的两个修改位于不同场景，分别从原版开始；Jinja M02 声明本场景 M01 的 code 依赖，必须承接真实已接受作业。37 个唯一任务的默认与分支试跑可形成66条路径、10次接受，仍只计37任务与6个唯一修改目标。
- 错误用法：把 `src/jinja2` 当模块名或使用已安装的 Jinja 代替候选。正确配置模块 `jinja2` 与相对导入根 `src`，并以实际 `__file__` 和完整节点合同核对；只读咨询没有候选文件时，移除不适用的候选证据 flag，保留可由公开资料支持的规则。

### 6. Tests Required

- 内容／历史／DTO：`test_project_scenario_content.py` 覆盖可变任务、非紧邻DAG、入口可达、隐藏投影、wheel损坏／链接、注册复开摘要、坏catalog历史可读、新600／旧1800默认及显式值／非法null；旧schema夹具回归保留。
- 语言修正：穷举正式首问、分支、材料说明、rubric 与运行时提示，核对英文语义及原授权／验收约束；比较修正前后的中文 `summary(include_steps=True)` 完全相等，新旧内容分别 install／复开仍按各自摘要读取。seed、固定业务输入、原生检查和 wheel 字节保持不变；Unicode 测试夹具与证据原文不作为必须翻译的正式指令。
- 状态／恢复／父链：`test_project_scenarios.py` 覆盖实际消费认领、澄清不加attempt、3次上限、工作高水位／崩溃预留、review三层预算、候选与review严格释放、完整输出quota／重启只续验收、迟到结果、文件交付进review包、局部轮换／分支激活、代码依赖恢复与不兼容／相同字节回退分支、实际模型漂移不扣业务修正。
- 协议／用量／私有运行：`test_project_evaluation.py` 覆盖严格单JSON／错误身份／重复项／未知证据／程序失败不能被pass覆盖、合法uncertain、显式candidate证据许可及缓存字段去重／未知；`test_project_review_runtime.py` 覆盖owner刷新身份、创建／停净／缺失／孤儿、清理失败保留holder及资源份额；`test_project_native_verifier.py` 覆盖准备阶段error、业务exit80为failed、清理前不放slot、合法等价程序提取。
- 原生内容：`python3 scripts/validate-project-library.py` 仅静态摘要／当前6-26-57；`scripts/validate-project-scenarios.py --project <key> --task <key> --image <隔离账号镜像>` 真实业务，按需 `--candidate/--answer/--entry/--branch/--expect failed`；`--regression-only` 或 `--with-regression` 使用独立回归资源。保留适用工程目标的原版失败／参考通过、原生完整集合与skip/xfail证据，不用宿主旧基线替代。
- 套件适配：`test_project_native_regression.NativeRegressionTests` 断言 src 叠加恢复原测试／配置、新 pytest hook 拒绝、旧默认不变、父链接与非法路径／模块拒绝、安装库错导入拒绝。目标镜像实际冻结并执行全部节点，再对每个参考候选跑完整适用回归；当前新增原版集合为228／911／81，数字是本轮实测记录，不作为后续套件的通用硬编码。
- 内容评审协议：逐任务及必要披露／无材料路径构造真实 `review_package` 并执行 `parse_review`，核证据标识与候选文件存在性；隐藏具体事实只有实际消费后可用于相应结论。模拟对账同时统计唯一码、路径、披露消费、业务尝试和接受父链，不能把分支或补充材料当作独立任务。
- Git 交付：`git check-attr text` 核对冻结数据 `unset`、普通代码保持原规则；`git check-ignore` 验证仅两个固定上游文件可追踪、本地工具文件仍忽略。用 `git checkout-index` 导出拟提交内容，核对文件全集、逐文件字节及 catalog 摘要，覆盖 CRLF 上游文件与被忽略的同名工具说明文件反例。
- 真实调度与UI：`deploy/v3/run_local_verification.py --manifest <隔离清单> --project-scenarios-only --scenario-capacity 1`，另测容量2；需要UI与失败恢复时加现有 `--scenario-browser`／`--scenario-failures`。核原Scheduler／driver／SQLite、holder容量、私有挂载与AT-only、超时半成品、仅续验收及页面状态／预算／用量对账；模拟CLI证据明确real_model_calls=0。旧project-iterations／project-scheduling、quota／window及普通题库适用回归继续保留。


## Scenario: 真实 GitHub 项目逐仓研究与百项目扩展 SOP

### 1. Scope / Trigger

- 选项目、研究 GitHub 仓库、编写场景与任务、扩充／替换项目库时适用。历史 100×20 工程路线研究作为来源保留；当前内容池方向为约 100 项目、600～800 场景／2,000 独立任务，每项目数量由真实场景决定，旧生成内容保持退役。
- 本节定义研究与准入流程；legacy `app.py` 协议与新场景原生适配分别按前述版本契约执行。已有三仓接入实现与本地证据不代表全部 100 仓已完成新场景或生产上线。
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

- 正常：`simonw/sqlite-utils` 固定 `9c66bafa52ae23d40499c74b0db3b635bcddb876`，原版全套测试 1,497 通过、16 跳过；相关原生测试在正式账号镜像隔离运行 75 项通过。二十步路线含 9 步已复现问题修复和 11 步功能增强提案；截至本节记录，尚未实施这二十步或完成平台原生接入。
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
