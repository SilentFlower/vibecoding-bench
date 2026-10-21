# Research: 内容契约、原生适配与分类验收

- Query: 将固定线性 20 步、app.py JSON 行验收扩展为数量可变的真实业务场景与稳定任务，需要哪些最小内容、分支披露和分类验收契约？现有语义评分、模型评审与人工审核能力能否复用？
- Scope: internal；外部项目仅依据已有固定源码与研究证据，不查询最新版。
- Date: 2026-10-21

## Findings

### 1. 结论与当前能力边界

1. 可以复用内容摘要、不可变 release、受限快照、候选隔离和原生会话证据；不能只取消 `minimum_steps=20` 就称为支持混合任务。内容当前只有线性步骤、统一开发提示、程序行为断言和“通过即更新代码检查点”，没有场景／材料披露／回答评审实体。
2. 没有找到可复用的语义问答评分器、方案评分器、独立模型评审调度或人工验收提交 API。`README.md:150` 仍把 LLM-as-judge 列为待 P3。现有正常 assistant 回复检测证明“回复已收口且属于当前输入”，不证明回复正确。
3. 自动独立模型评审与人工先审核都需要新增持久化评审契约；两者对自动推进、条件追问、CLI 资源持有和成本影响不同，必须由用户决定首版方式。本研究不代选。
4. 三份样板已经给出 13 个场景／20 个任务，包括 17 个非工程任务、两个库修复和一个用户应用增强；它们仍是设计稿，尚无新夹具、冻结评分器或模型完成证据。旧 100 仓／2,000 工程候选研究不应被重写成新内容已就绪。

### 2. 已发现文件

| 文件 | 职责与本次用途 |
| --- | --- |
| `orchestrator/project_library.py` | schema 1 加载、公开摘要、来源 seed 摘要与内容注册；主要内容契约改造点 |
| `orchestrator/project_verifier.py` | 无网络临时容器执行 app.py，控制端比较 JSON；原生及分类验收接入点 |
| `scripts/validate-project-library.py` | 当前 100×20 合成内容检查与参考运行时验证，不能直接验证新 QA 内容 |
| `orchestrator/project_plans.py` | 开发提示、原生输入／回复父链、逐步冻结、同步验收和接受事务 |
| `orchestrator/project_iteration.py` | 内容版本、实例单工作区、旧 schema 执行与成果读取 |
| `orchestrator/main.py` | 受控 Scheduler、共享账号并发／额度／身份、管理 API 与用量汇总 |
| `images/account/project_plan.py` | 账号侧同会话 driver；条件补充与评审等待需要同步适配 |
| `orchestrator/project_test_content.py` | 临时合成调度夹具，仅回归用途；不能迁回正式 catalog |
| `orchestrator/test_project_iterations.py`、`orchestrator/test_project_plans.py` | 内容、快照、验收、恢复、父链与共享容量的已知回归入口 |
| `project_library/catalog.json`、`project_library/README.md` | 当前正式库为空；README 中固定数量文字需在实现完成时同步更新 |
| `research/project-scenarios/{README,REVIEW,python-frontmatter,pydantic-settings,typer}.md` | 已确认场景样板、完成条件和材料披露；仅内容设计 |
| `research/github-projects/{python-frontmatter,pydantic-settings,typer}.md` | 固定来源、许可、原生基线、依赖与实际成本证据 |
| `webui/app.js`、`webui/index.html` | 现有步骤进度、成果及成本展示；没有人工评审动作 |
| `cc2api/src/service/runtime_bridge.rs` | 项目管理桥白名单；新评审资源如采用新路径须同步 |
| `images/v3/Dockerfile`、`images/v3/Dockerfile.dockerignore`、`deploy/v3/manage.py` | 正式内容打包及依赖／镜像集成边界 |

### 3. 代码模式与明确限制

#### 3.1 内容与公开摘要

- `ProjectLibrary.__init__()` 默认 `minimum_projects=100, minimum_steps=20`，只接受 schema 1（`orchestrator/project_library.py:216`）。`_validate()` 仍要求正 `source_topic_no`，固定 `entrypoint=["python3","app.py"]`，每步 `requires` 必须恰好等于前一个 ID（同文件 `:244`、`:251`、`:253`、`:267`）。这不是一般 DAG 校验。
- `_validate_cases()` 要求每步至少一个、最多 32 个 `{input: dict, expected: ...}`，无法表达回答事实、方案多解、条件披露或只读范围（同文件 `:273`）。
- `ProjectDefinition.summary()` 已采用字段白名单，不返回 `checks` 或 reference；可保留这种投影方式，但需为新场景／任务类型重建白名单（同文件 `:192`）。公开项目概要不应包含判定根因或隐藏分支答案。
- 内容注册保存 `releases/<digest>`，后续从固定 release 读取（同文件 `:282`）；快照摘要覆盖路径、内容和大小，忽略 `.git/__pycache__/.pytest_cache`，拒绝链接及特殊文件，树上限 128 MiB／10,000 文件（同文件 `:15`、`:98`）。快照恢复把普通文件设为 0644，不保存可执行位（同文件 `:148`），原生 shell 脚本若用现有机制应显式经 `bash` 调用，或另定义模式契约。
- `self.digest = snapshot_tree(root)` 对整个内容根做同一大小限制（同文件 `:241`），不能把所有真实仓库、完整 venv／wheel 缓存无界塞进这个目录。现有快照拒绝 symlink，也不适合直接打包常见带链接的 venv。
- `ProjectLibrary.install()` 复验时按已装项目最短路线传最小步数（同文件 `:300`）；新版本数量策略应一致修改加载／注册／测试，不能只改一个默认值。

#### 3.2 提示、验收与接受

- `_prompt()` 总是“Continue developing”，把第一个 `check` 的输入和 `expected` 直接发给候选，并规定标准库 app.py 协议（`orchestrator/project_plans.py:397`）。旧 schema `_reserve()` 有同样假设（`orchestrator/project_iteration.py:674`）。未来应从显式公开示例投放，隐藏 checks／rubric 不能自动取第一项变公开。
- `_evidence()` 可靠地验证固定 session、实际 user 输入、normal assistant 回复、父链以及回复后没有活动（`orchestrator/project_plans.py:528`）。可复用它取得回答证据；还需要保存对应回答文本／摘要，不能只保存程序快照与 token 边界。
- `_verify()` 冻结正在运行的候选，保存快照，累加当前之前所有步骤 checks，然后同步调用 verifier（同文件 `:567`）。对新内容，回归集合必须来自本场实际代码状态和已接受的代码能力，不能按全局任务索引把独立场景、只读问答的检查都累加。
- `_accept()` 将任何通过结果同时推进 `next_step_index` 并把当前树摘要写为 `checkpoint_digest`／`accepted_checkpoint_digest`（同文件 `:617`、`:641`、`:649`）。QA 通过应写回答结果；只有允许改动、验证成功的工程任务才接受新代码状态。临时咨询脚本／输出文档不应冒充工程能力检查点。
- 现有失败报告整份进入下一修复提示（同文件 `:409`、`:413`），`ProjectVerifier` 的失败详情包含输入、expected、actual（`orchestrator/project_verifier.py:113`）。新隐藏评测必须区分完整内部证据与可反馈摘要；公开业务规则可以解释，不能把所有隐藏样例／评分参考整份发回候选。
- 管理端 artifacts 目前返回完整持久报告（`orchestrator/project_iteration.py:891`），调用方是管理操作员。未来需明确“操作员可查”和“待测模型可见”的不同投影，不能将操作员详情整体拼进模型提示。

#### 3.3 原生执行

- `_EXECUTE` 固定 `runpy.run_path('app.py')`，`verify(candidate,cases,timeout=30)` 只执行 JSONL 行协议（`orchestrator/project_verifier.py:18`、`:56`）。`entrypoint` manifest 即使放开，也不会改变这里的真实执行。
- 隔离容器已有可复用边界：同批 account 镜像、UID 1000、无网络、无账号 HOME、候选只读挂载后复制、只读根、资源限制和有界日志（同文件 `:79`）。实际资源硬编码 256 MiB／64 PID，超时夹为最多 60 秒（`:84`、`:95`）。
- verifier 的 `failed` 是候选业务行为不满足；创建容器等异常归 `error`（同文件 `:97`、`:124`）。`ProjectPlans.verifier_report()` 对 error 最多本地再验一次（`orchestrator/project_plans.py:610`）。新增离线依赖缺失、评分器不可用、评审输出无法解析，不能变成模型代码修复请求。
- `scripts/validate-project-library.py:24` 总以默认 100×20 加载；`--all` 依赖正式库已退役的 `reference_runtime.py`，直接宿主运行 seed/app.py，并要求每项第一用例在基线不通过（`:25`、`:31`、`:44`）。QA 本来应在原版回答正确；只有工程修改目标需要证明起点未满足。验证新真实内容应走隔离原生适配器，不能把未知候选放宿主执行，也不能恢复旧参考运行时兜底。

### 4. 最小内容契约建议（提案，不是现有字段）

建议为新内容使用显式 schema 版本，与历史 schema 1 release 并存。以下为应表达的语义；字段名须在 design 中最终冻结，不预称现有 DTO 已定义。

| 层级 | 最小必需语义 | 静态校验重点 |
| --- | --- | --- |
| 内容发布 | schema、版本、项目键、发布摘要、适配／评分契约版本 | 非空可用项目集；不要求凑满 100 才试点；固定版本与摘要可回读 |
| 项目 | 真实仓库 URL、完整 commit、许可／归属、源码树摘要、运行环境档案 | 来源／许可证文件存在，源码和环境可重建；不能用旧 topic 序号当真实项目来源 |
| 业务场景 | 稳定 ID、真实用户目标、起始源码／应用／数据、会话延续策略 | ID 唯一；输入可隔离物化；同项目独立场景从指定基线开始 |
| 任务 | 稳定 ID、所属场景、五种使用类型之一、首问、可见材料、允许操作、结束条件、验收引用 | 至少一个有效任务，无统一步数；ID 不以数组位置作身份；不把消息和重试计新任务 |
| 依赖 | 需要的回答产物、已接受代码或业务数据分别声明 | 目标存在、无自环／重复／环；回答依赖不暗含代码依赖；独立运行时替代上下文必须预先冻结 |
| 条件补充 | 分支 ID、触发语义、公开材料引用、披露动作、合法下一状态／结束结果 | 所有引用存在；互斥／默认分支明确、追问有界；隐藏材料不会在初始 workspace 出现 |
| 权限边界 | 库源码、用户应用、输入文件、可写临时产物和工程修改范围 | 咨询示例允许写哪里；只读任务不得接受源码变化；库修复与应用增强分别检查 |
| 验收 | 类型、版本、隐藏 rubric／行为集摘要、回归集合、资源预算、反馈投影 | 可执行／可评审；多解与明确失败项存在；不是关键词包含或输出长度检查 |
| 运行预算 | 任务尝试／继续上限、累计有效执行预算；评测另列预算 | 恢复不重置；模型、原生验收及评审等待各有清晰计量 |

起始代码状态建议由“上游 commit＋实际源码树摘要＋用户应用摘要＋fixture 摘要＋环境档案”表示。后续接受状态另记录父状态和补丁／树摘要；`APP-R1`、`CP-UNION` 是本地状态标识，不能伪称新上游 commit。

依赖不能只把现有 `requires == previous[-1:]` 改成任意列表：调度必须按真实依赖决定 runnable；失败仅阻塞真正依赖任务，独立场景继续。记录回答继承时应指向已通过的回答产物，不从“最近 N 条目标”猜上下文。

场景完成要求其选定入口和合法分支的必要任务完成；未走分支记录未选择，不作为失败或新增任务。整轮结束可以含失败／预算耗尽／依赖受阻，需要与“场景全通过”分开统计。

### 5. 公开材料、隐藏评测与自然追问

1. 内容目录应明确分离可投放的源码、用户应用、初始材料、公开任务与控制端隐藏补充／验收。候选只收到当前首问及已披露材料，不能把研究样板原文复制进工作区；原文含全部答案。
2. 每次披露形成不可变事件：任务／入口／分支 ID、触发的真实回复证据、材料摘要、发送意图、消费确认和披露次序。重启只重放未确认动作；已消费不重发。这里复用现有原生父链、字节边界和输入消费证据，新增稳定轮次身份。
3. “请求复现／请求代码”是语义判断。不能以出现 `代码`、`bug`、`资料不足` 等词判定合理澄清，也不能强制用户问满三个问题。模型请求最小复现时可以一次提供完整相关材料。
4. FM-DG-01 的“资料拿不到”是冻结入口变体；模型不能自行宣称缺信息来切换该变体。PS-TRIAGE 的材料全部可提供，因此仅提问不能替代最终定位。TY-D02 请求注册代码或能确认归属的 help 都应触发同一组真实材料；help 应由同夹具产生，不能手编。
5. 模型正常结束一轮不等于任务结束：可以是请求补充、暂定假设、提交答案或提交补丁。控制端需先判定当前响应意图及允许分支，再继续披露或验收。信息不可得的合法结束应记录“恰当处理但根因未定位”，不可同时展示为已定位 BUG。
6. 问答不能因为未改码判失败；也不能因为答案合理就忽略未经授权的源码修改。验证受保护库／应用源摘要保持，允许单独目录的复现脚本、缓存及业务输出，不把这些全部算成违规或工程检查点。

### 6. 分类验收的最小输出

统一报告至少关联内容版本、任务／入口／分支、响应证据摘要、代码／fixture／环境摘要、验收器版本、各项判定与依据、总判定、可公开反馈及成本来源。这里只建议语义，最终状态名由整体设计统一。

| 类型 | 可机械验证部分 | 仍需语义判断部分 | 明确结束条件 |
| --- | --- | --- | --- |
| 理解 | 引用文件／符号在冻结源码中存在，源码保持 | 事实与问题相关、用途／流程／边界是否正确 | 关键事实完整且无实质错误；不要求补丁 |
| 咨询 | 提交的示例在临时目录真实运行，控制端检查输出／文件／输入未变 | 用法说明和适用边界是否与示例一致 | 给定业务目标达到；不将临时示例接受为工程能力 |
| 诊断 | 独立复现、对照行为、引用实际位置；披露事件顺序 | 材料是否足够、根因链是否成立、合理排除 BUG 或澄清 | 当前分支指定的根因／处理办法或有根据的不可定因结果 |
| 方案 | 引用 API／约束存在，必要小验证可执行 | 满足必需约束、可行性、取舍；允许多解 | 可行方案与边界足以决策，不要求偷偷实施 |
| 工程修改 | 固定源码范围差异、独立业务正反例、适用原生回归、真实加载路径 | 修改说明中必要的业务边界 | 行为和回归通过后才接受代码状态 |

事实引用存在只是辅助检查，不能证明叙述正确；出现正确符号名但结论相反仍应失败。回答简短不应扣分，长篇引用不应自动加分。行为测试通过也不能证明诊断理由和方案全部正确。

咨询示例需要一个可执行交付提取契约：明确一个主代码片段／文件集合及运行入口，或在允许的临时目录落盘后封存；TY-C01 当前明确“先不要创建文件”，须支持从答复取示例再在评测端执行。不能要求所有咨询都改工作区。提取失败标记未提供可执行交付，不把任意第一个 fenced block 当唯一程序。

### 7. 现有评分／人工审核能力检索结果

- 已检索 `orchestrator/`、`images/`、`scripts/`、`deploy/`、`webui/`、`cc2api/src/service/runtime_bridge.rs` 的 judge、rubric、evaluator、review、approve、score 及中文评分／审核语义，结合实际 API 和定义读取；没有发现任务语义评分器或人工判定提交能力。
- `orchestrator/main.py:2356` 的 similarity score 属于自然 prompt 候选去重／选择，不是答案评分；题库中含 Reviewer／rubric 的条目是被测业务题材，不是平台评审器。
- `ProjectVerifier` 的 `passed/failed/error` 是程序输出比较，不是独立模型语义判断。现有 artifacts 能展示记录（`orchestrator/project_iteration.py:891`），但没有审核身份、审核版本、审核动作或“待审核”状态。
- `README.md:150` 公开记录评测相关能力尚待 P3；不能从文档中的“人工 review 保质量”推断已有运行中的人工评分产品。

### 8. 两种首版路径及必需产品决策

| 影响 | 自动独立模型评审 | 人工先审核 |
| --- | --- | --- |
| 核心新增 | 持久评审作业、受控评审 Run、结构化判定解析、评分版本与成本 | 持久待审核条目、审核详情／动作 API／UI、操作记录、重复／过期防护 |
| 自动推进 | 正常回复后评审决定披露、通过／修正／结束；可自动继续 | 语义分支及最终回答需人处理；机械业务测试可自动，但不能默认语义通过 |
| 隐藏依据 | 独立上下文含冻结 rubric／相关源码证据／实际回答和已披露历史 | 操作员界面查看同一冻结依据；不给待测模型 |
| 成本 | 被测模型与评测模型 token／耗时分别记录；每次追问路由也可能有评测成本 | 不发生评测模型 token；仍有人工等待和工作量，不计入模型有效执行时间 |
| 不确定结果 | 解析失败／评审超时／依据不足应待复核或受阻，不能当候选失败 | 审核员可要求核实；未审核不能当通过，也不能默认为永久失败 |
| 大规模限制 | 可自动跑，但需先校准正确／错误／多解及不确定案例 | 数千任务的语义审核和动态披露会形成实际人工工作量 |
| 仍共有 | 冻结题目与依据、原生测试、只读检查、版本／分支／证据绑定、可恢复等待、独立结果与代码接受 | 同左 |

自动评审必须复用受控入口，具体证据与设计约束：

- `Scheduler.submit()` 是现有任务提交入口（`orchestrator/main.py:6393`），`_execute()` 使用同账号 semaphore（`:6746`、`:6789`）、运行窗口、账号身份和 quota 门禁；项目当前通过 `_execution_workload()` 映射到 normal 策略（`:3799`），manager 注入的就是 `scheduler.submit`（`:7847`）。
- 新评审类型若存在，必须在 workload／恢复／状态 API 中纳入同一门禁，不能加一个控制端 `requests.post` 直连模型或走独立不计并发的评审线程。原程序 verifier 的本地 semaphore 不是模型许可。
- 评审必须有独立评审会话／作业上下文及版本；不让候选在原会话自评自己的答案。评审输入只能来自冻结响应、材料和来源，不把候选断言当参考事实；模型评审也不能替代工程行为测试。
- **资源依赖需要显式改造**：当前 `_verify()` 在候选 CLI 冻结时同步验收，然后立即续投（`orchestrator/project_plans.py:567`、`:617`）。若同账号两个候选占满两个 CLI 许可，再同步等共享调度的评审，两者可能互等。应先持久保存候选／回答与原会话接续证据，严格释放本次执行，再排评审；评审就绪后按证据恢复待完成任务。人工等待也不能无限占着冻结 CLI。
- 这会影响“同一进程连续多任务”的优化边界：可保持会话和工作目录，长评审等待可能需要新 Run 接续；不能为了保留一个进程绕开共享容量或释放要求。

尚需用户决定的最小问题：首版采用自动独立模型评审还是人工先审核。若选自动，还需冻结评审模型／账号来源、自动结论权限、预算及无法判定时的处理；若选人工，需接受任务在语义分支处等待审核、确定由谁操作与怎样恢复。相同规则可先保持评审提供者抽象，但不能无决策就声称自动端到端完成。

### 9. 三项目的原生适配与资源依据

以下固定源码均实际读取相关定义；commit 与旧基线数字沿用已落盘证据。本研究未执行 Git、安装、原生测试或模型任务。

| 项目 | 已读源码事实 | 最小业务验收与环境边界 |
| --- | --- | --- |
| python-frontmatter `d2977d71638cb451bc06f2af3bb48e09e0dbe8c6` | `.deploy/github-100-research/resume-app/python-frontmatter/source/frontmatter/__init__.py:176` 的 `loads()` 把 metadata 展开给 `Post(content,handler,**metadata)`；`:306` 构造形参明确；`:75`／`:78`／`:95` 是 strip／浅 defaults／update | 只读理解和浅覆盖诊断可在 V0 完成；FM-IN-02 真实读写独立周报文件；FM-FX-01 修库并保持 content／handler 元数据及构造兼容。PyYAML 必需，TOML 非本样板要求 |
| Pydantic Settings `8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930` | `.../pydantic-settings/source/pydantic_settings/main.py:295`／`:323` 已有缓存／清理；`:336` 返回初始化、环境、dotenv、file 源顺序；`sources/providers/env.py:200` 的普通字段 Union 路径与 `:328` 原始字典注解路径不同 | PS-CONFIGURE 验 .env 与环境覆盖且数量为整数；TRIAGE 首轮隐藏消费端与实际输入；UNION-FIX 改候选库并验普通字符串／JSON 列表。环境／缓存／cwd 每场隔离，CLI 与远程来源不启用 |
| Typer `a5882dedf0bc7a46cd861fdfca020f88519e0f21` | `.../typer/source/typer/main.py:1173` 根据注册构造单命令或组；`:1530` 已有 parser／click_type，`models.py:335` 明确两者互斥；已内置 Click | TY-C01 从答复示例在临时评测目录执行；D02 由真实夹具产生 root／export help；M01 只改用户 shop.py、业务测试和文档，Typer 树摘要保持。控制端读回导出 JSON、核退出码／原文件／既有输出字节及 product 回归 |

上述 `...` 均指 `.deploy/github-100-research/resume-app/`，用于事实引用，不是未来可交付运行路径。正式夹具必须另行物化并固定摘要，不能依赖本机忽略目录或旧 `/tmp`。

已记录的依赖与成本：

- python-frontmatter：`research/github-projects/python-frontmatter.md:18` 起区分宿主 Python 3.12.3 原生与镜像 Python 3.12.15 业务观察。默认 56 加 11 个互斥严格 doctest 共 67，原默认 0.561 秒、安装 15.699 秒、venv 53,595,781 字节。冻结依赖含 PyYAML 6.0.3、pytest 9.1.1；既有 doctest 包装器未检查失败数，新原生回归不能只沿用该包装器。
- Pydantic Settings：`research/github-projects/pydantic-settings.md:13` 记录 1256 主项通过／5 skip，14.338 秒，宿主 RSS 348,636 KiB，venv 225,871,030 字节。此峰值大于现有 verifier 256 MiB，不能推断未来容器全套可通过。`requirements-recovered.txt` 包含原完整测试额外依赖，基础项目实际依赖在 `source/pyproject.toml:42`：Pydantic、python-dotenv、typing-extensions、typing-inspection；本地样板不需要启用云来源。是否裁剪验证环境要以冻结集合覆盖为依据，不能把少装包造成的 skip 当全套通过。
- Typer：`research/github-projects/typer.md:13` 记录完整上游集合 1481 主项通过／22 skip／2 xfail，181.272 秒，RSS 101,480 KiB，安装 11.947 秒、venv 55,754,642 字节。全套时长已超过 verifier 最多 60 秒。运行依赖是 shellingham、rich、annotated-doc，内置 Click 不需用外部 Click 代替。完整测试还需 coverage／xdist 等，并保留 `scripts/test.sh` 的 completion、terminal 及 strict 配置。

建议环境档案分别冻结运行依赖、任务行为验收依赖和适用原生回归依赖；准备阶段锁定完整版本／制品摘要／平台、离线 wheel 或同批镜像，验证阶段禁止临时联网安装。安装下载／构建成本、原生回归成本、待测模型用量和模型评审成本分别记录。

当前 `images/v3/Dockerfile:59` 的 account 层没有接入三仓专属依赖；不能假设镜像中已有。内容复制在 control 层 `:35`，`.deploy` 不进入镜像。若后续加入离线制品或运行配置目录，要同步 Dockerfile、dockerignore 和 `deploy/v3/manage.py:213` 的固定源码快照清单。dockerignore 末尾排除了 `**/.env`／`**/.env.*`，场景需要的 .env 应由已冻结业务素材显式生成并核对，不能指望同名文件自然被 COPY 保留。

业务验收与完整上游回归使用独立预算档案，预算需在目标镜像实测后定值。不能因 30 秒／256 MiB 默认过小而把环境错误归候选失败，也不能用删减集合冒充适用原生全套。任务级累计预算和评测预算分开，评审排队／人工等待不重置任务身份或模型尝试数。

### 10. 已知测试与应补验证

已知回归可复用，均未在本研究执行：

- `orchestrator/test_project_iterations.py:181`：正常退出但业务不符不能推进；`:207`：修复保留工作区及回归已接受能力；`:368`：验收基础设施故障不触发模型修复；`:418`：不可变历史和路径边界；`:440`：受限 umask 下候选可读；`:458`：旧合成库退役；`:475`：候选超时与 Docker 故障区分。
- `orchestrator/test_project_plans.py:123`：同 Run 多任务／逐步用量；`:191`：超时只补余步；`:302`：局部失败不阻兄弟；`:315`／`:331`／`:349`：会话、代次与检查点拒绝；`:402`：父链顺序；`:423`：验收期间停止／重复决定；`:452`／`:465`：消费证据与禁止盲发；`:755`：历史 DB 迁移幂等。
- `deploy/v3/verify_project_execution.py`、`verify_project_scheduling.py`、`verify_project_catalog.py`、`verify_project_browser.py`：现有真实 Docker／driver／调度／页面回归入口；其合成模型不证明真实问答效果。

新内容与评审应补的有效验证：

1. 3 项目／6、7、7 任务的首批内容可加载；少于 20 项、不相邻依赖、独立场景可执行；重复／不存在依赖／环被拒绝；历史 schema 1 能回读。
2. 初始候选目录／提示不含隐藏复现、rubric 或参考答案；正确澄清触发同一材料，关键词乱提与重复索要不通过；披露消费后重启不重发。
3. 正确无 BUG／多种可行方案可通过；包含正确符号但事实相反、捏造 API、遗漏硬约束或未经授权改库均失败。机械引用检查不能单独判通过。
4. 咨询示例在评测端运行，原输入不变，临时输出不产生代码检查点；库修复导入候选库，用户应用增强导入固定 Typer，核对实际 `__file__`／环境档案，不能导入另一份已装版本。
5. 修改前证明目标未满足、修改后独立正反例及原生回归成立；使用受控验收源，不依赖候选自报或其可删改测试。
6. 同一响应重验幂等；旧 generation／旧候选／旧 rubric 的评审回包不能接受；停止期间评审结果保留为历史但不推进。
7. 自动方案验证两个候选占满账号容量时评审不死锁，等待不绕额度／窗口／并发，评测 token 不计入待测任务；人工方案验证未审核不通过、重复提交／过期审核不推进。
8. 候选完整而验收未完成时只恢复验收；评审／验证超时可恢复冻结输入，不重新请求被测模型。基础设施失败不消耗业务修正次数，累计有效预算跨恢复不重置。
9. 对所有入口与合法条件分支完成冻结验证后才标 ready；逐项报告设计完成、适配可用、模型通过和部署状态，不借旧研究数字填充新运行结果。

### 11. 受影响文件与相关规范

- 内容 schema／加载／公开投影：`orchestrator/project_library.py`、`project_library/README.md`、新 schema 2 正式内容及其独立控制端验收材料；正式 catalog 只在对应内容物化并验证后接入。
- 按类型提示、分支和评审等待／接受：`orchestrator/project_plans.py`、`orchestrator/project_iteration.py`、`images/account/project_plan.py`；数据表和整体恢复设计由本任务其他研究共同收敛。
- 分类／原生验收：`orchestrator/project_verifier.py`、`scripts/validate-project-library.py`；宜通过有限、显式适配类型扩展，执行受控验证入口，不开放候选任意 shell 作为判分器。
- 自动评审方案还涉及 `orchestrator/main.py` 的受控作业类型、调度／恢复和成本；人工方案还涉及提交判定 API、`webui/app.js`／`index.html` 的待审核视图。两者均需更新成果与状态投影。
- `cc2api/src/service/runtime_bridge.rs` 如新增 API 资源则同步白名单；`images/v3/Dockerfile`、`.dockerignore`、`deploy/v3/manage.py` 需同步内容／制品打包。
- 现有测试夹具与测试文件扩展；三份研究样板保留来源，正式运行内容与其保持可对账，不能把样板 Markdown 直接当候选 prompt。
- 主要规范 `.trellis/spec/vibecoding-bench/backend/project-iterations.md:76`／`:163` 是旧运行协议／旧 100×20 研究 SOP。用户最新确认已取消强制每仓 20 项；规划需明确新旧版本语义，后续通过 update-spec 更新当前接入契约，保留旧研究历史口径。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md:80`／`:90`／`:98`／`:108` 分别约束内容隔离、共享门禁、证据接受、离线验收；仍需保持。
- 本次已读 `.trellis/workflow.md`、后端 index、上述完整项目迭代规范及本任务 `prd.md`。当前 planning，研究不能代替 Brief 审阅或实现许可。

### 12. 外部来源与版本

本轮不依赖外部最新版信息；源码事实来自已存储的完整固定提交，对应官方主源：

- `https://github.com/eyeseast/python-frontmatter/tree/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6`；关键定义位于 `frontmatter/__init__.py`、`default_handlers.py`，依赖见 `pyproject.toml`。
- `https://github.com/pydantic/pydantic-settings/tree/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930`；关键定义位于 `pydantic_settings/main.py`、`sources/providers/env.py`、`sources/utils.py`，包版本 2.16.1。
- `https://github.com/fastapi/typer/tree/a5882dedf0bc7a46cd861fdfca020f88519e0f21`；关键定义位于 `typer/main.py`、`models.py`、`testing.py`，包版本 0.27.3。

## Caveats / Not Found

- 没有找到现成语义评分器、独立评审任务或人工审核流；以上两条首版路径都是待实现选择，不能称已支持。
- 三仓新场景夹具、条件分支、咨询示例提取器、冻结 rubric、原生适配与目标镜像资源证据尚未制作。旧宿主全套通过不是新镜像全套通过。
- 本研究没有运行安装、测试基线、真实模型或付费实验；没有执行 Git 操作、修改正式代码／库／规范、提交推送或部署。写入范围仅本文件。
- 原生源码位置与旧依赖文件是本机研究证据；正式运行不得以这些路径作为跨机器交付保证。来源 SHA 与基线统计依照已落盘报告引用，本轮未重做 Git 取证。
- 内容字段和状态建议尚不是正式接口。自动或人工评审的首版选择、评审预算／模型、分支路由及不确定结果处理仍需产品决策后进入 design。
