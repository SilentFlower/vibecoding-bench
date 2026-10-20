# 项目迭代模式技术设计

## 1. 边界与既有事实

本任务交付一个完整的新模式，包含内容库、持久项目实例、自动推进器和独立页面；内容与运行闭环须共同满足验收，不把只有题目文本的目录当作可运行项目库。

已核对入口：

- `orchestrator/main.py`：`TaskIn`、`BatchIn` 和原创建接口以 topic 为入口；`tasks.topic_no` 为非空整数，`topic_id/batch_id` 可空。
- `Scheduler.submit/_execute`：负责窗口等待、账号信号量、凭据、共同额度、启动及收口；当前多个分支只识别 `normal/warmup`，新增类型必须显式接入普通任务策略。
- `QuotaGuard.policy_snapshot/admit/recover`：已有类型限定和恢复逻辑，不改变 `normal/warmup` 对外含义。
- `AccountRuntime.start_run/_project_view/run_session_path`：目前按环境与 run ID 定位目录和主会话；新模式必须同时改变新实例的目录和会话定位。
- `images/worker/entrypoint.sh`：`RESUME_SESSION_ID` 会覆盖输入为恢复原任务的控制文本，因此只用于原步骤额度恢复，不用它投递下一步骤。
- `webui`：原生 JavaScript、hash 页面、既有运行详情及 SSE；不引入前端框架或构建系统。

新增文件、字段和路由以下文契约为准。实现验证发现统一后台还有资源白名单，须同步扩展 `cc2api/src/service/runtime_bridge.rs` 的项目管理资源；保留内部路径拒绝与会话鉴权，不修改模型转发协议或账号数据库。

## 2. 项目内容库与发布版本

### 2.1 内容结构

新增 `project_library/`，每个项目具有稳定的 `project_key` 和独立目录：

```text
project_library/
  catalog.json
  projects/<project_key>/
    project.json
    seed/
    verification/
```

- `catalog.json`：内容版本、100 个项目键及项目摘要。
- `project.json`：标题、分类、来源题号、基线摘要、运行说明、阶段和步骤定义。来源题号只记录内容出处，不用于恢复时重新读取题库。
- `seed/`：可直接启动的初始代码、固定且明确标记的合成数据、启动说明。首版优先使用当前镜像已有的 Python 标准库、SQLite、Node 和原生 HTML/JS，避免运行期必须下载依赖或取得外部凭据。
- `verification/`：基线与步骤的行为输入、预期结果、回归组和内容质量验证资料，仅由控制端读取，不复制给执行模型。

每步包含稳定 ID、业务目标、修改边界、前置步骤、所属阶段和验收组；执行时限由批次策略固化。首版每项目至少 20 步，按业务里程碑组织；阶段必须有明确终点，不能使用大量同义的“优化”或靠更换名称凑数。

统一适配层只负责启动、传递合成输入、收集结构化输出；不同项目必须具有各自的业务规则、核心操作和路线。允许共享脚手架，不允许 100 个项目只有数据标签不同。内容分组与示例路线见 `research/catalog-scope.md`。

### 2.2 一致性与版本固定

控制端首次注册目录时，将规范化 manifest、源码、样例和验收定义存入 `BENCH_DATA/project-library/releases/<digest>/`，原子发布且随后只读。该目录不挂载到账号环境，不属于用户可见工作区。构建时将内容库复制进 v3 control 镜像，运行时注册为不可变版本。

`seed_digest` 对相对路径与文件字节计算，覆盖初始代码和数据，不以 mtime、账号 ID 或批次 ID 参与计算。拒绝路径越界、符号链接、特殊文件、重复 ID 和摘要不一致；实例不得从活动题库或新版内容重新生成基线。

项目升级发布新 digest；旧批次继续绑定旧内容，历史版本在仍有引用时保留。检查源码相同与业务可运行是两项不同验证，均须完成。

### 2.3 内容的可验收性

- 100 份初始版本全部运行基线用例。
- 每个步骤有独立的行为断言，并回归此前已接受的能力；不使用文件存在、源码关键词或模型“已完成”作为唯一证据。
- 用控制端的参考行为／参考修改序列证明全部步骤的通过条件可达到，且基线不能被错误认定为所有步骤已完成。
- 参考资料仅用于离线内容验证，不进入模型工作副本；其通过不能代称真实模型已完成 2,000 步。

## 3. 持久化契约

新增四张 SQLite 表，主键均使用现有整数自增约定，时间显式写 UTC Unix 秒。下表定义核心字段；实现时同步补齐必要的错误原因、索引和参数校验。

| 新表 | 核心字段与约束 |
| --- | --- |
| `project_catalog_releases` | `id, version, digest UNIQUE, relative_path, created_at`；版本不可原位修改 |
| `project_iteration_batches` | `id, account_id, name, catalog_release_id, status, policy_json, active_instance_id, generation, stop_requested_at, next_launch_at, created_at, updated_at`；一个批次属于一个账号 |
| `project_instances` | `id, batch_id, project_key, manifest_json, seed_digest, roadmap_digest, status, next_step_index, workspace_relative, started_at, checkpoint_digest, visit_order, created_at, updated_at`；`UNIQUE(batch_id,project_key)`；未开始的路径和启动时间均为 NULL |
| `project_step_attempts` | `id, instance_id, step_id, attempt_no, run_id UNIQUE, expected_checkpoint_digest, execution_released_at, validation_status, result_digest, report_relative, accepted_checkpoint_digest, created_at, ended_at`；`UNIQUE(instance_id,step_id,attempt_no)` |

每次尝试仍建立真实 `tasks/runs` 并由现有 Scheduler 执行，`run_kind='project_iteration'`。尝试表唯一关联 `run_id`，不复制两套权威 run 身份。

首版内容全部取自已存在的题库领域，`tasks.topic_no` 保存冻结的来源题号以满足现有非空契约；`tasks.topic_id/runs.topic_id` 与原 `batch_id` 均为 NULL，不能加入原题库补充或原批次调度。项目身份始终由尝试表与实例表关联，不以来源题号定位工作区或进度。新项目任务在页面显示项目和步骤，不显示为旧题库任务。

迁移仅新增表、索引和必要的可空兼容字段，不重建原表，不回填旧 prompt、身份或路线，不修改账号凭据和 cc2api 数据库。所有写入沿用 `_db_lock`、事务、参数化 SQL；文件复制、Docker 和验收在锁外执行。

## 4. 自动推进与切换

### 4.1 调度策略

新增 `ProjectIterationManager`，使用现有进程的 daemon 线程和 SQLite 状态，不引入外部队列。

- 创建批次只创建 `not_started` 实例记录；默认处于暂停状态，显式启动后自动推进。
- 每个账号同时最多执行一个新模式步骤，并继续参与既有账号总信号量和维护租约。
- 每个批次默认维护最多三个尚可推进的活动项目；继续当前项目到该项目定义的阶段终点，再在活动项目间轮转。有活动名额时才选择下一个未开始项目，不一次展开 100 个目录。
- 完成阶段、项目局部阻塞或路线完成会记录切换原因；额度和账号认证属于账号级阻断，不能靠切换项目继续执行。
- 初次执行后最多追加两次修复尝试。每次尝试默认沿用现有 1,800 秒任务时限；额度恢复是同一尝试的执行代次，不消耗一次新的业务修复名额。
- 所有项目完成后批次结束；全部剩余项目不可推进时记录 `blocked`，不循环制造模型请求。批次停止或账号身份变化使旧 generation 不能再投放、验收提交或推进。

`policy_json` 固化上述批次策略；不通过随机按键或任意等待伪装交互。项目池数量、活动项目数量、账号并发和任务时限分别计量。

### 4.2 状态与完成依据

`runs.status` 保持现有执行语义，正常退出仍只说明模型执行结束。业务接受状态保存在 `project_step_attempts.validation_status`，可为 `pending/running/passed/failed/error/cancelled`。只有通过验收且代次、父状态和预期 checkpoint 全部匹配时，才能在事务内推进实例。

实例状态为 `not_started/ready/running/quota_wait/window_wait/blocked/completed/stopped`。批次状态为 `paused/active/pausing/stopping/stopped/blocked/completed`；认证原因和局部失败原因另行记录，不用字符串推导权限。

暂停先进入 `pausing` 并禁止新投放；已运行的步骤可完成并验收，若进入额度等待则暂停恢复，收口后变为 `paused`。再次启动延续该未完成尝试。立即停止则持久化停止意图、撤销本代推进权并终止在途执行，不能按暂停语义继续发请求。

同一步最多接受一次，以已接受步骤及 checkpoint 为准。重复通知不重复保存进度；相同报告摘要重放只读取原结果。

## 5. 按需工作目录与会话

### 5.1 首次启动

只有在共同额度、窗口、账号信号量、维护租约和批次代次均通过，并进入本次实际启动后，才由新模式准备实例工作副本。

准备过程先在控制端私有临时目录核对基线并复制，再原子发布到账号环境 `projects/<alias>`；发布时记录实例的 `workspace_relative/started_at`。alias 由环境与实例 ID 稳定派生，不按新 run 改变。若在发布前失败，临时目录不进入工作区；发布后启动失败属于已开始的失败现场，持续保留。

文件系统与 SQLite 不伪装成单一原子事务：发布标记记录实例、初始版本摘要和目标路径，启动代次保存在尝试表并在发布前重新校验；重启后先核对标记再补齐数据库。无法归属的已发布目录保留并阻塞，不删除、不覆盖，也不能当作尚未开始重新复制。

原有 `_project_view` 对普通 run 保持原行为；新模式通过尝试记录解析稳定实例，再建立当前 run 的兼容链接。`Runner.start_run` 不能在新模式仍等待门禁时提前创建空的 run 工作目录。

### 5.2 后续步骤与恢复

后续轮次只读取现有实例目录，不重新复制 seed。控制端保存已验收代码与数据的内容摘要和只读 checkpoint，失败现场另存；中止或切换不覆盖当前工作副本。checkpoint 使用按文件摘要复用的对象与清单，避免每轮无条件保留整份重复数据。

项目持久化与聊天历史分开：新步骤／业务修复使用新主会话和有限上下文，输入包含当前目标、已有成果摘要及必要失败证据；不重发完整 20 步路线。原步骤的额度恢复继续使用原 run、输入与会话。

`run_session_path` 和 `_find_latest_claude_session_id` 对新模式同步接入实例定位与本次执行字节基线。共享 cwd 的历史 JSONL 不能误认成当前 run 已消费的输入；尚无本次会话时不得恢复上一已完成步骤的主会话。

目录不会因项目完成、暂停、切换、容器重建或服务重启而删除。首版不提供自动删除或清理已开始项目的功能。项目目录链接只在 `workspace_relative` 非空时展示；项目库和未开始记录可以在独立列表浏览。

## 6. 自动验收与成果提交

新增控制端验收适配器。它持有不可变用例，通过 Docker 启动无凭据验证环境，仅挂载本次源码／数据快照和必要的临时可写数据目录；不共享账号 HOME、账号网络、Docker socket 或模型凭据。

复用同批 account 镜像中的运行时并显式覆盖入口；验证容器采用独立用户、无外网、资源与超时限制。控制端只启动被测程序并采集其结果，不在控制进程 import 或执行模型生成代码。预期结果和最终通过判定由控制端保存，不接受程序自行输出的 `passed=true` 代替断言。

验收前必须确认原执行已严格清理并归还租约，再写入 `execution_released_at` 并封存候选快照。仅观察到 `runs.status` 终态不能触发验收或下一步；清理失败保留现场并阻塞，避免旧子进程继续写入。

步骤验收对本次候选快照检查新增行为及前序能力。默认使用副本中的合成数据，验证过程不能污染持续工作区。通过后保存源码／数据摘要、验收报告、代码差异和 checkpoint，再通过条件更新提交进度。

验收失败将精简且有界的错误证据作为下一修复尝试输入；达到上限则保留当前失败现场与最后通过版本，阻塞本项目后继步骤。验证器自身故障记录 `error`，不能当作程序业务失败或通过；基础设施故障只进行有界本地重试，不因此无限发起模型修复。

## 7. API 与页面

新增以下路由，沿用现有 cookie 鉴权、Pydantic 与中文错误反馈：

| 接口 | 用途 |
| --- | --- |
| `GET /api/project-catalog` | 项目、发布版本、基线和路线摘要 |
| `POST /api/project-iteration-batches` | 以 `account_id,name,project_keys` 创建暂停批次，固定内容版本 |
| `GET /api/project-iteration-batches` | 批次、账号、进度、门禁和当前实例 |
| `GET /api/project-iteration-batches/{id}` | 实例列表、活动项目、未开始项目与切换原因 |
| `POST /api/project-iteration-batches/{id}/start` | 首次启动或恢复暂停批次，重查身份与状态 |
| `POST /api/project-iteration-batches/{id}/pause` | 禁止新投放，保留在途步骤完成和验收，随后暂停 |
| `POST /api/project-iteration-batches/{id}/stop` | 持久化停止意图、停止当前执行并禁止恢复 |
| `GET /api/project-instances/{id}` | 路线进度、已有目录、checkpoint 和尝试记录 |
| `GET /api/project-step-attempts/{id}/artifacts` | 受限的报告、版本清单和差异，不接受任意宿主路径 |
| `GET /api/project-iterations-stream` | 页签活动时的状态摘要推送，不扫描全部原生日志 |

新增“项目迭代”hash 页面，包含项目库、批次及实例详情；既有页面和默认入口保持。模型执行状态、业务验收状态、窗口／额度等待、当前阶段和修复次数分开展示。

运行详情增加项目归属和只读成果入口。新模式不允许通过原“再次运行／继续对话”绕过路线或实例写锁：后端对新模式任务做明确校验并引导至项目批次入口；原有 task/run 行为不变。历史项目文件从当时 checkpoint 查看，当前工作目录另行标注，不能把最新文件冒充旧轮次成果。

tokens 复用现有已记录的成功请求统计，按尝试与步骤汇总；缺失显示未知，不发额外模型探测或额度查询，也不把目标输出量当成已实现事实。

## 8. 共同执行、恢复与兼容

新 run 类型通过统一的内部映射接入 `normal` 额度策略，覆盖首次执行、准备后复查、quota_wait、恢复、正常收口与认证失败；不向 `QuotaGuard.policy_snapshot` 直接传入未知字面量。

新批次父状态检查覆盖 Scheduler 的投放前、信号量后、凭据准备后、额度恢复与验收提交，而不只在页面按钮检查。窗口／额度等待不占实际执行资源，也不提前建目录。

启动顺序为：数据库与内容注册 → 现有账号／额度事实对账 → 新批次和尝试对账 → 开启新投放。对已结束但未验收的尝试重新执行幂等验收，不重复生成模型请求；对在途尝试先严格清理并核对原输入、会话、代次和快照，状态不明则保留现场并阻塞，不能猜测成功或重新初始化。

停止、软删除和重授权检查加入新批次及已开始实例引用，避免账号被硬删后遗留无所有者项目。已有账号维护和其他模式继续使用原锁序，不能持全局数据库锁等待 Docker 或文件操作。

## 9. 交付与回退

- 预置内容与新模块随同批 control 镜像交付；account 镜像保持原账号生命周期，验证容器不进入账号环境池。
- 本地使用隔离数据和合成服务验证，不自动触碰生产环境或用真实账号执行全量 2,000 步。
- 首选回退是暂停／停止新批次并保留新模式数据，恢复使用原题库入口；不删除已开始目录或内容版本。
- 若必须回退不认识新类型的旧二进制，需先收口全部新模式在途与等待任务，使用 SQLite backup API 保存一致快照，并隔离旧页面对新模式历史的再次执行入口；不能直接整库覆盖后续账号或任务数据。

## 10. 验证与取舍

- 内容目录核对 100 × 20、步骤依赖、初始版本摘要和独立业务覆盖；运行全部基线及参考路线验收。
- 状态机通过真实 SQLite 和隔离 Docker 场景验证并发认领、验收后推进、重复事件、修复上限、停止竞争、额度／窗口恢复及目录延迟出现。
- UI 使用真实 API 和浏览器核对 1280／390px、明暗主题、无工作路径的未开始项目、已开始目录持续保留及 XSS。
- 实际模型通过率与用量需功能投入运行后测量。先用少量项目、相同模型和 effort 比较每响应、每完成步骤及每有效执行小时的输出，再决定是否扩大日常投放；这不减少本次 100 项目的交付范围。
