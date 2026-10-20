# 项目迭代模式契约

## Scenario: 冻结内容、持久实例与自动业务验收

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
ProjectIterationManager.create_batch(account_id, name, project_keys=None, policy=None)
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
| `POST /api/project-iteration-batches` | 原账号、名称和项目键，加严格整数策略字段；API 总是创建 schema 2 |
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

**内容与版本**：`project_library/catalog.json` 为 schema 1；每个项目包含 `project.json`、可运行 `seed/` 和控制端 `verification/`。当前适配协议固定为 `python3 app.py`，逐行输入／输出 JSON。基线代码必须具有自己的业务核心；通用算法与启动脚手架可以复用。每步依赖紧邻前一步并属于明确阶段。

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

control 镜像的项目库、`images/v3/Dockerfile.dockerignore` 放行项、`deploy/v3/manage.py` 的源码快照列表须同步。`PROJECT_LIBRARY_DIR` 可覆盖内容路径，容器默认 `/repo/project_library`；损坏内容只使新模式返回 503，不替换旧题库入口。账号删除引用计数包含新批次，不能将尚无 run 的项目批次变成孤儿。

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

- `python3 scripts/validate-project-library.py --all`：数量、依赖、摘要；全部 seed 真正运行；待开发步骤不能在基线通过；所有参考断言可达到。参考器另有手写业务金标准用例。
- `test_project_iterations.py`：同账号不同批次及不同账号基线一致、修改隔离；100 元数据零目录；两步累积、失败修复与旧能力回归；三项目阶段轮换返回；重复接受、停止竞争、额度暂停恢复及重启；认证／清理失败阻断；不可变历史、路径和主日志边界。
- `test_project_plans.py`：严格策略、实际容量 1、固定随机队列、2＋2＋1 轮换、共享容量与持久间隔；同 Run 两步、逐步 token、业务修复、停止竞争、重复决定及父链乱序；1／2 超时接续、原 Run quota_wait、检查点／会话缺失与截断、确认丢失和禁止盲发；旧结构主键／索引／序列幂等迁移。
- 文件／停止回归：发布边界实际UID1000读取、相同决定inode不变、缺失补发、普通文档0600；open与fstat间替换、持续替换上限、非法文件与fd关闭；初始终态／SQL认领前独立连接终态／新代次／清理中终态不覆盖，不重复清理、不伪造释放，局部blocked首次原因与健康补位。
- `ProjectVerifier`：独立 Docker 正例／反例、程序超时与基础设施错误区分；控制端 umask 不影响 UID 1000 读取候选。
- `deploy/v3/run_local_verification.py --manifest <清单> --project-iterations-only`：合成 CLI 经过真实 Scheduler、driver、会话、清理和 Docker 验收的两步闭环。不得当作真实模型能力证据。
- `deploy/v3/run_local_verification.py --manifest <清单> --project-scheduling-only`：真实 Docker／driver／tmux 中两个 CLI 重叠、冻结 A 时 B 继续、同 Run 两步及 60 秒真实 timeout 后只补剩余一步；Tasks 两 CLI 和既有 passthrough 长连接跨补位／清理保持。多个验收入口顺序创建独立网络，避免测试子网竞争。
- `deploy/v3/verify_stack.py --manifest <清单> --browser --project-iteration`：真实 UI/API/SQLite，目录等待与重启保留、XSS、SSE 状态保持、1280/390px 明暗主题。
- `--project-scheduling-only`还须验证定向局部阻塞后兄弟及原队列后续项目继续。`--project-catalog-only --evidence-dir <新目录>`为可选100×20长测，保持默认10秒稳定等待并独立对账；部分运行不能记为全库通过。中断先停止本次标签下的写入容器，再清临时目录，保留证据及精确清理结论。
- 原 `--run-boundaries`、`--topic-followups` 分别回归；新管理桥运行 `cargo fmt --check` 与 `cargo test --locked`，保留内部路径拒绝断言。
