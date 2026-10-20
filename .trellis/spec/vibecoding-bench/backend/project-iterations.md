# 项目迭代模式契约

## Scenario: 冻结内容、持久实例与自动业务验收

### 1. Scope / Trigger

- 修改 `orchestrator/project_{library,iteration,verifier}.py`、`run_kind='project_iteration'`、项目管理 API、`#projects` 页面或项目内容打包时适用。
- 本模式依赖 v3 固定账号运行环境；普通题库、批次、养号、抓包和续聊继续使用原有身份及状态语义。
- 内容、路线和业务验收归本文件；Docker 账号角色、租约、认证及原额度恢复继续遵守 [account-runtime-v3.md](./account-runtime-v3.md) 与 [database-guidelines.md](./database-guidelines.md)。

### 2. Signatures

控制端入口：

```python
ProjectLibrary(root, minimum_projects=100, minimum_steps=20)
ProjectLibrary.install(data)
ProjectIterationManager.create_batch(account_id, name, project_keys=None)
ProjectIterationManager.transition(batch_id, action)
ProjectIterationManager.prepare_workspace(row, run_id, environment_root)
ProjectIterationManager.execution_released(run_id, quota_attempt, error=None)
ProjectVerifier.verify(candidate, cases, timeout=30)
```

API 均位于原 cookie 鉴权下：

| 方法／路径 | 输入或结果 |
| --- | --- |
| `GET /api/project-catalog` | `version,digest,projects`，项目摘要含 `project_key,seed_digest,step_count,milestones` |
| `GET /api/project-catalog/{key}` | 公开目标与依赖，不返回参考实现 |
| `POST /api/project-iteration-batches` | `{account_id: StrictInt,name: StrictStr,project_keys: list[StrictStr] \| null}` |
| `GET /api/project-iteration-batches[/{id}]` | 批次的 `status,policy,counts`，详情另含 `instances` |
| `POST /api/project-iteration-batches/{id}/{start\|pause\|stop}` | 返回最新批次详情 |
| `GET /api/project-instances/{id}` | 路线与尝试；执行状态、`validation_status` 分开 |
| `GET /api/project-instances/{id}/usage` | 按步骤聚合尝试，缺失证据为 null；`complete` 仅表示各尝试都有记录 |
| `GET /api/project-step-attempts/{id}/artifacts` | 固定报告、摘要、文件清单和可用的版本差异 |
| `GET /api/project-step-attempts/{id}/file?path=...` | 清单内文件的有界文本预览 |
| `GET /api/project-iterations-stream?batch_id=...&instance_id=...` | `project-state` SSE；实例必须属于所选批次 |

`name` 默认“项目迭代批次”，去除首尾空白后为 1～120 字符；项目选择不可空、重复、超出 100 项或不属于当前版本。省略项目键表示全选。

SQLite 的 `PROJECT_SCHEMA` 由 `init_db()` 幂等执行，新增：

- `project_catalog_releases`：`digest UNIQUE`，固定发布路径。
- `project_iteration_batches`：账号、创建时身份、内容版本、`policy_json,generation,status,active_instance_id`。
- `project_instances`：`UNIQUE(batch_id,project_key)`，冻结 manifest、基线／路线摘要、`next_step_index,workspace_relative,started_at,checkpoint_digest,visit_order`。
- `project_step_attempts`：`run_id UNIQUE`、`UNIQUE(instance_id,step_id,attempt_no)`；保存代次、预期 checkpoint、执行释放证据、候选／报告／已接受摘要。`validation_status='passed'` 的实例与步骤另有部分唯一索引。

每次尝试创建原 `tasks/runs`，`runs.run_kind='project_iteration'`；来源题号只满足旧 `topic_no` 非空契约，原 `topic_id/batch_id` 留空，不加入旧路线或补充调度。

### 3. Contracts

**内容与版本**：`project_library/catalog.json` 为 schema 1；每个项目包含 `project.json`、可运行 `seed/` 和控制端 `verification/`。当前适配协议固定为 `python3 app.py`，逐行输入／输出 JSON。基线代码必须具有自己的业务核心；通用算法与启动脚手架可以复用。每步依赖紧邻前一步并属于明确阶段。

内容首次注册到 `BENCH_DATA/project-library/releases/<digest>`，旧批次固定旧版本。账号只复制 `seed/`，不挂载参考器或冻结验收目录。内容摘要覆盖相对路径和字节，不包括账号、mtime；拒绝链接、特殊文件及越界路径。快照上限为 128 MiB／10,000 文件，JSON 文件上限为 4 MiB。

**自动调度**：创建批次默认 `paused`，只建立元数据。启动后每账号最多一个未收口的项目尝试；默认三个可推进的活动项目、最多两次追加业务修复、每次 1,800 秒。当前项目先完成内容定义的阶段，再轮换；没有活动名额时不提前开始第四个项目。局部失败保留现场并切换；认证、身份变化或严格清理失败阻断批次。路线耗尽完成，不无限生成后续任务。

批次状态为 `paused/active/pausing/stopping/stopped/blocked/completed`。暂停禁止新投放，已运行步骤可以完成并验收；额度等待的原尝试保留，恢复沿用同一 run。停止先持久化意图并增加 generation，终止在途执行；停止、阻塞、完成的批次不再启动，须另建批次。

**共同门禁与目录**：新类型通过 `_execution_workload` 映射到 `normal` 额度策略。窗口等待、账号信号量之后、凭据与环境准备之后、实际 exec 之前均复核门禁；不得创建独立模型调用通道。`can_start` 还核对账号可用性、冻结身份和父批次代次。

实例的 `workspace_relative/started_at` 初始为 NULL。只有进入实际启动才从控制端 staging 发布到 `environments/<environment_id>/projects/<alias>`；alias 由环境与实例 ID 固定派生。发布标记保存实例、基线摘要和目标路径，代次由尝试表及发布前检查约束。发布中断后核对已有归属，不删除或覆盖未知目录。后续步骤只复用原目录；暂停、阶段切换、完成、停止和服务重启均不清理项目文件。

**会话和用量**：新步骤／业务修复使用新主会话，提示只包含本步、近期成果和有界失败证据。额度恢复沿用原 run/session。共享 cwd 的主日志以本轮 `native-start.json`／`native-end.json` 字节边界分隔，响应按 message ID 去重，排除 sidechain/meta。缺起点、截断或无可靠统计时显示未知，不能计入整个项目历史；页面也不主动探测模型用量。

**验收与成果**：必须等待原执行严格清理、释放资源并写入匹配 `quota_attempt` 的 `execution_released_at`。单有 `runs.status='success'` 不能验收或推进。候选封存到控制端内容对象与清单，验收不修改持续工作副本。

验证容器复用同批 account 镜像，显式覆盖入口、UID 1000、无网络、只读根、无账号 HOME／凭据／Docker socket；候选只读挂载，复制到临时可写目录运行。默认 30 秒，内存 256 MiB、PID 64，输入及输出有界。控制端比较行为结果并回归基线和此前全部已接受能力，不能信任程序自行宣告通过。

`validation_status` 为 `pending/running/passed/failed/error/cancelled`。程序超时／错误输出属于业务失败；验证基础设施故障最多在本地验证两次，不投递模型修复。通过后事务同时校验父状态、generation、步骤下标和预期 checkpoint，并依赖唯一约束防止重复接受。失败快照和最后通过版本同时保留，历史文件通过清单读取，不能用当前目录冒充旧成果。

**集成与交付**：项目 API 的五类资源必须同步加入 `cc2api/src/service/runtime_bridge.rs` 白名单，保留内部路径和编码穿越拒绝；不得扩展鉴权豁免。`#projects` 复用 `RUNTIME_BASE`、API helper、主题变量及转义；离开页签关闭 EventSource，推送重绘保留滚动位置和路线展开状态。

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
| 原执行终态已落库但尚无严格释放证据 | 不封存、不验收、不投递下一步 |
| CLI 退出正常但行为失败 | 不推进，在原目录有限修复；用尽后阻塞实例并切换 |
| 验收期间停止或旧 generation／checkpoint 回包 | 不接受结果，不增加进度 |
| 已发布目录缺失、归属不明、链接或快照损坏 | 保留现场并阻塞，不重置 seed |
| 请求历史文件越界或文件不在清单 | 404；不读任意宿主路径 |

### 5. Scenarios and Examples

- 正常：创建 `{ "account_id": 1, "name": "本地迭代", "project_keys": ["project-001", "project-002"] }`，两个实例路径均为空。启动后只出现第一个实际执行实例；第二步继续修改第一步保留的源码。
- 边界：已完成阶段后切到第二个项目，再返回第一个时继续下一未完成步骤。暂停和额度等待只保存进度；停止后目录仍可检查。
- 错误用法：每个新 run 重新复制 seed，或直接用退出码零推进步骤。正确做法是按实例复用目录，等待严格释放，再对控制端冻结行为验收。
- 错误用法：用整个共享 cwd 的 JSONL 计作本轮 token，或把参考路线通过称为真实模型完成。正确做法是使用 run 字节边界；真实模型通过率和用量单独观察。

### 6. Tests Required

- `python3 scripts/validate-project-library.py --all`：数量、依赖、摘要；全部 seed 真正运行；待开发步骤不能在基线通过；所有参考断言可达到。参考器另有手写业务金标准用例。
- `test_project_iterations.py`：同账号不同批次及不同账号基线一致、修改隔离；100 元数据零目录；两步累积、失败修复与旧能力回归；三项目阶段轮换返回；重复接受、停止竞争、额度暂停恢复及重启；认证／清理失败阻断；不可变历史、路径和主日志边界。
- `ProjectVerifier`：独立 Docker 正例／反例、程序超时与基础设施错误区分；控制端 umask 不影响 UID 1000 读取候选。
- `deploy/v3/run_local_verification.py --manifest <清单> --project-iterations-only`：合成 CLI 经过真实 Scheduler、driver、会话、清理和 Docker 验收的两步闭环。不得当作真实模型能力证据。
- `deploy/v3/verify_stack.py --manifest <清单> --browser --project-iteration`：真实 UI/API/SQLite，目录等待与重启保留、XSS、SSE 状态保持、1280/390px 明暗主题。
- 原 `--run-boundaries`、`--topic-followups` 分别回归；新管理桥运行 `cargo fmt --check` 与 `cargo test --locked`，保留内部路径拒绝断言。
