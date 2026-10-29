# Research: 正式场景内容、打包与文档同步草案

- Query: 核对正式三项目、README、Docker／源码快照路径及 planning 三件套与当前实现的差异，提供可审阅的中文同步草案。
- Scope: internal；只读产品代码、内容及本任务文档，仅写本研究文件。
- Date: 2026-10-21

## Findings

### 1. 当前正式内容的可核对事实

`project_library/catalog.json:1` 已为 `schema=2`、`version=real-project-scenarios-v1`，不是空库。`ProjectLibrary.__init__` 在 `orchestrator/project_library.py:224` 分流新旧内容：schema 1 保留原项目数量下限；schema 2 只要求至少一个就绪项目。新内容不要求每项目 20 个任务，也不走 `app.py` JSONL 入口。

| 项目键 | 固定来源提交 | 场景／任务 | 类型分布（理解／咨询／诊断／方案／修改） |
| --- | --- | --- | --- |
| `python-frontmatter` | `d2977d71638cb451bc06f2af3bb48e09e0dbe8c6` | 4／6 | 1／1／2／1／1 |
| `pydantic-settings` | `8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930` | 5／7 | 1／1／3／1／1 |
| `typer` | `a5882dedf0bc7a46cd861fdfca020f88519e0f21` | 4／7 | 1／2／2／1／1 |

合计 13 场景、20 任务，其中 17 个非工程任务、两个上游库修复及一个用户 CLI 应用增强。任务总数与选定入口的必要任务数不同：例如 FM 的 `consult_only`、PS 的 `diagnose_only`、Typer 的 `understand-only` 会缩小本次选择。内容总数不能直接当批次成功分母。

来源与许可实物在各 `project.json` 的 `source` 和 `seed/library/LICENSE`；Typer 额外列出 vendored click 与 Pydantic 许可。此处只确认本地固定声明及文件存在，没有重新访问上游网站核验历史。

本次只读命令：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate-project-library.py
```

退出码 0，输出为 3 项目／13 场景／20 任务，检查时摘要为 `bea64281e71ec7fd4fd699bf3cd635198ac453b998c6c2a3f29053b58c3784bd`。此摘要会随本轮继续修复而变，不宜写成 README 的固定承诺；此命令仅证明结构与制品摘要，不证明运行链路或模型通过。

### 2. 两个需要实现者处理的正式准入缺陷

#### DOC-BUILD-01：Typer 固定 `.env` 被两层打包规则移除

- 文件：`project_library/projects/typer/seed/library/.env`，131 字节；只有 `TERMINAL_WIDTH` 一个赋值键及注释，是固定上游源码的一部分。未在输出中披露文件内容。
- `snapshot_tree`（`orchestrator/project_library.py:99`）将它纳入源码清单；当前 Typer `seed_digest` 为 `fd8db542b38dd5da63cdbd625dc964acd6648da242cec842bd161b84c8fa852b`。
- `deploy/v3/manage.py:216` 的 `shutil.ignore_patterns(..., '.env', '.env.*', ...)` 会从源码快照移除它。
- `images/v3/Dockerfile.dockerignore:35` 的 `**/.env` 又会从直接 Docker 上下文移除它。仅修其中一层仍会漏文件。
- 仓库根 `.gitignore:1` 也默认忽略名为 `.env` 的文件；本研究未查 Git index，若选择保留固定原文件，还必须核对它是否真正进入精确提交范围。
- 直接从真实快照清单删去该条后重算，摘要为 `1973831264e54d740cec31e27561ebc6ced0ce3ed27f0265472c692de527e110`，与 manifest 必然不一致。因此本地宿主加载成功不能推导完整构建成功。

扫描全部正式内容 1,083 个文件、68,116,650 字节，无符号链接；按当前源码快照忽略模式，唯一被移除的正式文件就是该 `.env`。88 个 wheel 均不匹配忽略模式。

建议实现者选择一个明确方案：将该固定非敏感测试输入改为不会被全局忽略的冻结素材，在受控适配端生成，并同步 seed／contract 摘要和回归；或者为这个精确、已核对的固定路径在源码快照及 Docker 忽略规则同时增加例外。不要取消所有 `.env` 保护，也不要假称缺失文件不影响发布内容身份。若移动／删除 seed 文件，必须同步正式 `seed_digest`、原生 baseline contract 与相关校准证据。

#### DOC-CONTENT-02：Typer Python 档案与候选启动的精确版本门禁冲突

- `project_library/environments/typer-py312/profile/profile.json:1` 当前 `python` 为 `3.12`，同时 `observed_python` 为 `3.12.15`。
- `orchestrator/account_runtime.py:1503–1505` 调用 `platform.python_version()`，再与 `profile['python']` 精确字符串比较，目标镜像返回 `3.12.15` 时必然拒绝正式 Typer 候选启动。
- 应按真实目标镜像证据将冻结值修正为完整 `3.12.15`，然后重新做静态内容校验／摘要与实际候选准备验证；不要放松为任意主次版本匹配而绕过既有冻结契约。

这两个问题均已即时消息通知主会话。此文件记录的是发现时快照；主会话并行修复后应更新状态，不能把本研究中的旧摘要当最终摘要。

### 3. 打包路径已有覆盖与缺口边界

| 入口 | 当前实际覆盖 | 判断 |
| --- | --- | --- |
| `images/v3/Dockerfile:31` | `COPY orchestrator/*.py ./` | 新场景、评审、usage、native regression 模块自动覆盖，无须逐模块增加 COPY。 |
| `images/v3/Dockerfile:33` | `COPY project_library /repo/project_library` | 正式项目、素材、verification、环境 profile 与 wheel 均在复制根内，但受 `.dockerignore` 上述例外影响。 |
| `images/v3/Dockerfile.dockerignore:24–30` | 放行 `orchestrator/*.py` 与 `project_library/**` | 新模块、88 个 wheel 无类型过滤；后置 `.env` 规则优先，故不能只引用放行项作为通过证据。 |
| `deploy/v3/manage.py:214–218` | 冻结 folders 已含 `orchestrator`、`images/account`、`images/worker`、`project_library` | 新模块／driver／内容已有根覆盖；唯一发现的正式材料排除是 `.env`。 |
| `deploy/v3/manage.py:223–226` | 对快照中相对路径及各文件内容摘要汇总 | 被忽略文件不进 source_content_sha256；仍需检查快照内 ProjectLibrary 能加载。 |
| `images/v3/Dockerfile:107` 附近 | 账号镜像显式 COPY `images/account/project_plan.py` | 新 driver helper 的正常完整构建路径已有覆盖；本轮派生本地验证镜像不等同完整发布构建。 |
| `orchestrator/Dockerfile` | 旧镜像仅复制 main 与 quota_protocol | 这是旧交付入口；本场景运行依赖 v3，不能把旧 Dockerfile 单独构建结果当新内容交付证据。 |

建议补一个无需完整昂贵 Rust 构建的打包验证：用正式 snapshot 忽略函数生成受控快照，再在其中执行 `ProjectLibrary` 静态校验；另以真实 Docker context 复制内容后核对摘要。证明这两层均保留同一内容即可，不为“同步”而改已经全覆盖的 wildcard。

仓库根 `.gitignore` 不忽略 wheel；研究只读取该文件，没有执行任何 Git 操作，未核验当前 index 中这些二进制是否已跟踪。提交前仍应由主会话按精确范围检查 88 个冻结 wheel 是否实际纳入交付。

### 4. 实际内容格式应同步进 design 与规范

`orchestrator/project_scenario_content.py:10` 是 schema 2 的实际定义，建议补充下列可执行字段，不继续只列抽象“场景／输入／验收”。

| 层次 | 当前实际字段／约束 |
| --- | --- |
| catalog | `schema=2`、`version`、非空且唯一的项目键数组 `projects`。 |
| project | `schema`、`project_key/title/category/description`、`seed_digest`、`source`、`environment`、`scenarios`；source 为 HTTPS GitHub、40 位 commit、seed 内许可文件。 |
| scenario | `id/title/goal/default_entry/entries/tasks`；entry 为 `id/task_ids`，可带固定 `materials/setup`。 |
| task | `id/kind/goal/prompt/requires/materials/allowed_paths/outcomes/evaluation`，`max_turns` 默认 4、范围 1～8，另可带 `setup/branches`。 |
| dependency | `{'task_id': ..., 'artifact': 'answer'|'code'}`；当前明确拒绝跨场景依赖，code 仅可引用 modify。规划应写清首版限制。 |
| setup | 精确 `source/target` 两字段；source 为 materials 或披露目录内固定文件，target 仅可写 `app/`。task、entry、branch 都已接受此格式；执行完成度须另核对。 |
| branch | `id/when/materials`，可带 `setup/activate_tasks`；激活只能同场景已有任务，全部 task 必须在某入口／分支可达。 |
| evaluation | `version/rubric`，可选 `native/semantic`；modify 必须有 native；不能因 rubric 存在就认为评审质量已校准。 |
| native specification | `script/args/python_paths/expected/resource_profile`，工程目标带 `regression.runner/contract`；旧 `argv/cwd` 说明并非实际最终执行的唯一依据。 |
| environment | `environments/<id>/profile/profile.json`，`schema=1, adapter=python-native, python, business, regression, artifacts, requirements`；每项 artifact 是相对 `artifacts/` 路径＋SHA-256，requirements 精确 `name==version`。 |

实际白名单摘要在 `scenario_summary`（`orchestrator/project_scenario_content.py:234`）：目录公开项目身份、来源、`content_schema/scenario_count/task_count`，详情可再有场景及任务 `id/kind/goal/requires`；不公开首问 prompt、隐藏 branch、rubric 或全部 project.json。文档不应写“直接向页面返回完整任务定义”。

新项目按项目快照，离线环境另存，catalog 摘要包含 catalog、逐项目摘要及环境 profile；`ProjectLibrary.install`（`orchestrator/project_library.py:322`）分别物化项目对象与 wheel，再重新校验注册摘要。单源码树 128 MiB／10,000 文件仍保留；单环境最多 2 GiB／256 个制品，每制品读入上限 256 MiB。不能笼统描述成“整个库受 128 MiB 上限”。

### 5. 实际新增表与设计差异

`orchestrator/project_scenarios.py:26` 的 `SCENARIO_SCHEMA` 当前有 **9 张表**，design 第 5 节只列了前 8 张；应补逻辑计划表，并明确执行来源与计时的字段，避免恢复约定仅留在代码。

| 表 | 当前关键实际字段／约束 |
| --- | --- |
| `project_scenario_instances` | `instance_id,scenario_key,entry_key,definition_json,workspace_relative,session_id,seed_digest,checkpoint_digest`；实例＋场景唯一。 |
| `project_scenario_tasks` | `task_key,kind,selected,status,phase,turn_no,attempt_count,infra_recoveries,next_reason,next_prompt,result_json,input_checkpoint_digest,accepted_checkpoint_digest`；场景＋稳定任务唯一。 |
| `project_task_attempts` | `task_id,attempt_no,reason,consumed_at,ended_at,result`；实际消费后建立，任务＋attempt_no 唯一。 |
| `project_task_executions` | `run_id UNIQUE,task_id,attempt_id,plan_id,role,evaluation_job_id,review_attempt,turn_no,generation,session_id,delivery_id,resume,result_json,ended_at`；candidate 在任务内至多一个未收口执行。 |
| `project_execution_sources` | `execution_id,quota_attempt,source,delivery_id,native_relative,cwd,request_relative,decision_relative,evidence_start_json,evidence_end_json,work_relative,released_at,execution_error,start_permitted`；执行＋quota＋source 唯一。 |
| `project_task_deliveries` | `task_id,phase_key,prompt,input_digest,status,input_key,consumed_source_id,consumed_at`；任务＋phase_key 唯一；表默认 status 是 `pending`，设计抽象 sending/sent/consumed 不宜伪称完整数据库枚举。 |
| `project_evaluation_jobs` | `task_id,source_id,turn_no,generation,response_key/response_digest,input_digest,basis_digest,candidate_digest/candidate_relative,answer_relative,evidence_json,version,status,native_result_json,review_result_json,review_attempt,infra_recoveries,review_resume,response_budget_sec`；来源＋回答＋版本唯一。 |
| `project_work_segments` | `source_id,segment_seq,role,boot_id,start_mono,reserved_sec,confirmed_sec,status,usage_json,settled_at`；来源＋序号唯一；status 限 reserved/active/settled/uncertain。 |
| **`project_scenario_plans`** | `scenario_instance_id,generation,task_ids_json,passed_ids_json,status,created_at,ended_at`；同场景至多一个未结束逻辑计划。 |

design 逻辑计划边界本身已有描述，增加第九张表属于实现落点的同步，不是新需求审批。`initialize_scenario_schema` 当前仅执行 CREATE IF NOT EXISTS；它能从旧生产无新表状态创建新表，并不自动升级本轮中途出现的更早新表结构。若开发／恢复测试使用中途 DB，需明确其升级策略或只用独立临时数据，不能泛称任意新旧开发快照已迁移验证。

### 6. 模块、资源与 API 文档实际差异

- design 模块职责应补 `project_review_runtime.py`（私有容器／身份副本／所有者刷新／严格释放）、`project_scenario_usage.py`（逐 source 原生用量）和 `project_native_regression.py`（三仓固定回归控制脚本）。`project_evaluation.py` 主要是范围／评审包／协议／证据解析，不应独占叙述整个运行调度实现。
- 正式三份 `verification/native_regression.py` 与控制端 canonical wrapper 当前完全同 SHA-256：`3bbf34e44c67ae040ade28f601634f7ef61af9c8f38da6fad1cb4e6cf8cd6ec0`。应写清权威来源及复制一致性校验，防止三份受控脚本将来漂移。
- 评审资源不是临时给原 CLI 追加额度：`scenario_account_limits`（`orchestrator/resource_budget.py:46`）静态从原预算扣 512 MiB 给单 review 池，固定 CLI 仍至少 512 MiB；network 256／sender 128 MiB，额外 swap 仍只给固定 CLI。总 RAM 最低需要 1,408 MiB。PID 原 CLI 512 拆为 384＋128，CPU 原 CLI 6/8 拆为 4/8＋2/8，池容量 1。
- `ProjectReviewRuntime.check_layout`（`orchestrator/project_review_runtime.py:214`）对旧已创建容器不会静默降限；缺 layout 时要求空闲显式重建环境。README／运行前提应说明，不能承诺旧环境立即自动具备新评审能力。
- `ProjectIterationBatchIn`（`orchestrator/main.py:10169`）已增加 `scenario_entries: project_key -> scenario_id -> entry_id`，设计 API 一节应列明。它不属于 policy；真正创建按 `exclude_unset=True` 保留省略，schema 2 内容默认候选 600 秒。DTO 的 `timeout_sec=1800` 只是旧默认，不能直接写成新默认。
- 新 nested 路径准确为 `/api/project-instances/{iid}/scenario-tasks/{tid}/attempts|artifacts|file`；artifact/file 接受可选 `evaluation_id`。tid 是内部场景任务行 ID，稳定业务 task_key 是另一字段，调用方不能混用。
- 三仓环境 Python／平台元数据有命名漂移：FM 的平台为 `linux-amd64`，其他是 `linux/amd64`；验证状态字段分别为 verification_status、status、validation_status。目前 validator 没把这些状态当统一执行准入。应规范稳定字段，或在文档明确它们只是来源取证元数据；不要用三个不同字符串直接推导全局 ready。

### 7. planning 三件套建议按当前事实同步

1. `prd.md` Background 中“尚未物化新夹具或独立验收”已过时。可改成“已物化三项目冻结内容及离线环境；原生校准、调度机制和模型完成分别记录，真实模型完成数仍为 0”。不因已写代码直接勾选 AC1–AC9。
2. `design.md:7` 的“新增均为待实现契约”可改为“本文为目标契约；当前落地与验证状态见 implement/research”，避免把已经存在的 API／表仍写成不存在；仍保留未完成部分的明确状态。
3. design 第 3、5、7、10 节补以上实际格式、同场景依赖限制、逻辑计划第九表、资源静态预留和 scenario_entries；第 12 节补本轮已发现的 `.env` 两层打包问题及修复证据。
4. `implement.md` 起首“当前 planning”与当前 task in_progress 不符；阶段复选框应只根据相应实际测试／证据勾选，不全勾。建议按“内容静态／真实原生／状态单测／真实 Docker 模拟／UI跨层／Check-All”分别链接证据。
5. 实际新增机制验证入口已经是 `deploy/v3/run_local_verification.py --project-scenarios-only --scenario-capacity {1,2}`，应加入计划实际命令；旧 `--project-iterations-only`／`--project-scheduling-only` 保留作兼容验证，不替代新链路。
6. `scripts/validate-project-library.py:29` 当前对新库 `--all` 明确拒绝，提示“独立原生场景校验入口”，但本次搜索未找到对应正式开发 CLI。需要提供真实入口或把文案改成存在的可运行命令；不能在 README 放尚不存在的命令。
7. `brief.md` 的 Next Step 仍为“首次审阅通过后激活”，可小幅同步为当前实现与验证阶段，无需重新整份 Brief 审批。
8. 已存在 `research/native-regression-calibration/completion-audit.json`：FM 67 passed（11 doctest）、PS 1256 passed＋5 skip、Typer 1481 passed＋22 skip＋2 xfail，固定 wrapper 校准已保留反例。这些是本地原生证据，不是三项目模型通过数。PS native spec 仍有 `draft_status/status=not_executed`，应按每个真实业务脚本的具体证据更新，不能因为回归过就把未独立执行的业务项一并改成 passed。

### 8. README 中文替换草案

以下正文可替换 `project_library/README.md`；实施者先修复上述准入缺陷，最后根据最终验证状态调整“当前证据”段，不要未经核验宣称端到端全部通过。

````markdown
# 真实项目场景内容库

当前正式清单采用内容 schema 2，包含三个固定版本的真实开源项目，共 13 个业务场景、20 个独立任务。任务覆盖理解、咨询、诊断、方案与明确授权的工程修改；每项目的数量由真实业务决定。

| 项目 | 场景 | 任务 | 工程目标 |
| --- | ---: | ---: | --- |
| python-frontmatter | 4 | 6 | 修复正文／handler 同名元数据的处理 |
| pydantic-settings | 5 | 7 | 修复嵌套字典 Union 环境变量解码 |
| Typer | 4 | 7 | 增强用户商品导出 CLI，库版本保持固定 |

共 17 个非工程任务与 3 个工程任务。固定入口可选择不同任务集合；补充材料、正常澄清、超时继续和修正均不增加任务数。100 个项目、约 600～800 个场景和约 2,000 个任务是后续内容池方向。

## 内容组织

- `catalog.json`：内容版本和就绪项目键。
- `projects/<key>/project.json`：固定来源／许可、场景入口、任务依赖、授权范围和验收引用。
- `projects/<key>/seed/`：场景初始库源码、应用和必要许可。
- `projects/<key>/materials/`：任务开放材料；`disclosure/` 为按冻结分支披露的补充材料。
- `projects/<key>/verification/`：控制端私有 rubric、业务验证、固定回归控制脚本及 contract。
- `environments/<id>/profile/profile.json` 与 `artifacts/`：固定 Python、资源档案、精确依赖和离线 wheel 摘要。

候选只获得固定源码、当前问题及应披露业务输入；隐藏参考、rubric 和评审包不进入候选工作区。通过问答只记录任务结果；工程任务通过授权范围、独立行为和适用原生回归后才接受代码检查点。

新内容使用执行策略 schema 3。正常回复先封存候选并严格释放，再进行程序验收和必要的同模型独立会话评审。评审复用原账号／模型与共享容量，私有 HOME、输入和日志独立；用量和预算单独记录。现有账号环境需要匹配评审资源布局后才能运行。

## 本地校验与证据

从仓库根目录运行静态校验：

```bash
python3 scripts/validate-project-library.py
```

该命令检查内容结构、固定源码和离线制品摘要，并报告项目／场景／任务数量。它不调用模型，也不代表原生行为或运行链路已通过；新内容不使用旧 `--all` 参考运行时。

完整原生与调度验证应使用项目实际验证入口，并分别记录目标镜像、命令、通过／跳过、资源和来源。当前保留了三仓原生回归校准材料；真实模型会话完成数仍为 0。内容制作、接入验证、本地模拟模型机制和真实模型成绩分别报告。

## 兼容与交付

旧 schema 1 内容、旧策略和已冻结发布按原版本读取；当前 catalog 不可用不应遮蔽历史批次与成果。旧 100 个生成项目、生成器和参考运行时保持退役；调度回归合成夹具只在测试临时目录生成，不计入真实项目规模。

内容按固定摘要注册到数据目录，离线环境与源码对象分开保存。新增内容与素材须同时通过 v3 Docker 上下文和源码快照规则核对；业务 `.env` 按冻结素材准备，避免忽略规则造成内容缺失。源码修改不代表已经发布、部署或删除历史数据。

项目运行规范见 [项目迭代规范](../.trellis/spec/vibecoding-bench/backend/project-iterations.md)，初始场景设计见 [三项目场景样板](../research/project-scenarios/README.md)。
````

### 9. 相关文件与规范

- `.trellis/workflow.md`：阶段、角色只读边界、依据实际证据推进的规则。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md`：现有运行／历史／真实来源准入契约；其中空库和100×20当前态需在 owning Update-Spec 阶段同步。
- `.trellis/spec/vibecoding-bench/deploy/index.md`、`image-build-push.md`：构建和交付边界；本研究未发布镜像或部署。
- `orchestrator/project_library.py`、`project_scenario_content.py`：真实内容、快照、摘要与白名单定义。
- `orchestrator/project_scenarios.py`：九表、delivery/source/plan/预算和机械验收真实落点。
- `orchestrator/account_runtime.py`、`project_review_runtime.py`、`resource_budget.py`：Python 精确匹配、私有评审和静态资源要求。
- `images/v3/Dockerfile`、`Dockerfile.dockerignore`、`deploy/v3/manage.py`：正式复制根与快照忽略规则。
- `scripts/validate-project-library.py`：已执行的静态校验；schema 2 的 `--all` 尚无替代正式 CLI 指引。

外部参考只采用本地 manifest 已冻结的来源 URL：`https://github.com/eyeseast/python-frontmatter`、`https://github.com/pydantic/pydantic-settings`、`https://github.com/fastapi/typer`。本次工作不需要对外部最新版本作判断，未进行互联网检索。

### 10. 原生适配器与问答评审链路增量复核

- Query: 只读复核 `verify_native`、`_mechanical_job`、正式 native spec、固定回归 contract、问答评审输入与只读归属。
- Scope: internal；不重复三仓原版全套或三工程原版／参考验收，不调用模型，不改产品。
- Date: 2026-10-21

#### 10.1 已从真实接线确认的边界

1. `ProjectScenarios._mechanical_job`（检查时 `orchestrator/project_scenarios.py:1208`）先核对来源释放、执行收口、父代次、候选树摘要与授权范围；有 native 时先执行业务观察，状态 error 仅本地再试一次；业务 passed 且有 regression 才调 `verify_native(..., regression=True)`，回归 error 也仅本地再试一次。回归状态实际并入最终机械判定，不是只存一个声明。
2. 机械 failed 直接进入有限业务修正，error 进入评测受阻；非 modify 才进入同模型私有评审，modify 默认不额外做语义评审。`parse_review` 不允许 pass 覆盖非 passed 的机械结果。这里的“modify 默认直接接受”也是下面用户测试缺口会成为实际漏验的原因。
3. `verify_native` 回归模式从冻结 `regression.runner/contract` 生成参数，分别挂载 `/source`、`/baseline`、`/offline`、`/request-data` 与 `/request-data/verification` 为只读。脚本来自控制发布项目而非候选；使用 UID 1000、无网络、只读根、全 capabilities 移除。候选执行副本位于隔离 `/work/project`，不修改持久业务工作区。
4. `native_regression._run`（`orchestrator/project_native_regression.py:320`）真实核对 baseline 文件摘要、project/schema、Python 和插件版本，然后从固定 baseline 构建测试树：FM／PS 仅叠候选实现包，恢复原版测试控制，FM 还恢复原版 doctest 文本；Typer 要求库树完全固定。实际跑 pytest 子进程，核对 collection、逐节点结果、JUnit、skip/xfail、加载路径及 Typer Bash 父进程。
5. 控制端另核 wrapper 的 passed、真实退出 0、`collection_matches_contract=True`、节点数量和 collection digest。真实 wrapper 还要求完整 nodes（含 outcome）与 contract 相同。调查时没有发现“仅信任命令退出 0 便通过固定回归”的问题。
6. 回答内容与当前任务已消费对话、rubric 均绑定摘要；输入超过 512 KiB 明确受阻，没有静默裁剪后作确定评分。`source_evidence` 从固定发布目录读取真实文本，不从候选可写目录取 rubric。当前完整对话已在实现中，不能再沿用早期“只看本轮短prompt”的旧发现。

#### 10.2 NATIVE-01：用户应用测试只检查存在，未验证实际断言／执行结果

- 位置：`project_library/projects/typer/verification/native_checks.py:349`。
- 现状：`business_tests_present = tests.is_dir() and any(tests.rglob('test*.py'))`。即使文件为空或内容为 `pass`，该字段仍为 True；脚本没有收集或运行 `app/tests`。
- 明确要求：TY-M01 首问要求“补充针对业务行为的测试”，rubric `delivery_scope` 又要求“有真实业务断言的用户测试”。三仓上游回归 wrapper 只运行固定 `library` 测试集合，不能替代用户应用测试。
- 实际影响：工程业务代码正确、README 含三个关键词、放一个空测试文件，就可能经过机械观察和固定库回归后被直接接受；modify 默认 `semantic=False` 不会让评审补查此项。另一个反例是候选 app/tests 中存在故意失败断言，当前也不影响验收。
- 建议：为应用测试增加独立受控收集／执行与有效测试证据；本地回归至少包含“空文件”“纯 pass”“明确失败断言”三负例。不能仅将 `any(test*.py)` 改为搜索 assert 字符串冒充可运行业务测试。
- 验证范围：由代码和明确 rubric 对照确认，未重跑完整三仓。已即时通知主会话。

#### 10.3 NATIVE-02：允许文件交付的咨询示例未进入私有评审包

- 位置：`ProjectScenarios._package`，检查时 `orchestrator/project_scenarios.py:1269–1284`，以及 `project_evaluation.source_evidence`。
- PS-CONFIGURE 的公开 `materials/configure-delivery.md` 明确允许“只在回答中给代码，或写到 app/settings_example.py”；FM-IN-02 同样允许 `app/example.py`。
- 机械验收会从冻结候选读取这些实际文件，但评审包只放 `answer/conversation`、固定 `source_evidence(project.root, rubric)` 和程序观察结果，没有候选文件／diff 内容。来源证据中的 library 是固定 seed，不是任务生成的 app 文件。
- 反例：回答仅“已放入 app/settings_example.py，请使用该文件”，文件内有正确完整代码。机械行为可以通过，但评审需要判断真实 API、完整主示例和交付边界时看不到该代码，会被迫依赖观察摘要或判 uncertain。这会误拒绝合法文件交付，不能把“回答必须复述文件全文”当隐藏前提。
- 建议：从 `candidate_digest` 对应冻结清单中，有界加入当前任务实际交付的源码／必要 diff，校验每个文件摘要；超限保持受阻。不要为补评审上下文把隐藏 rubric 放回候选。
- 验证范围：由实际包字段与公开交付规则确认；应补“正确文件＋简短回答”及“文件正确但回答说法错误”的评审输入对照。已即时通知主会话。

#### 10.4 NATIVE-03：合法 Typer 类型注解示例被 AST 识别器误拒绝

- 位置：`project_library/projects/typer/verification/native_checks.py:175–206`，launches 只收集顶层 `ast.Assign` 赋值目标，没有 `ast.AnnAssign`。
- 最小反例：同一完整合法程序只把 `app = typer.Typer(add_completion=False)` 改成 `app: typer.Typer = typer.Typer(add_completion=False)`。两者仍以 `app()` 启动，参数与业务行为完全相同。
- 实际执行了纯识别器检查（未运行候选程序／模型／容器）：用 `runpy.run_path` 载入固定控制脚本，`ast.parse` 两种程序，再调用 `_complete_programs`。退出码 0，结果为 `plain: recognized_programs=1`、`type_annotation_only: recognized_programs=0`。
- 影响：TY-C01 native 输出 `consult_sample_found=False`，直接业务失败；rubric 明确允许不同合法 Typer 接入形式，因此这是确定的等价答案假阴性。
- 建议：识别已支持的合法初始化形式，包括 AnnAssign；以真实行为作最终依据。保留这个最小变体为回归，不需要重跑原生 1505 节点集合。已即时通知主会话。

#### 10.5 NATIVE-04：准备阶段与业务阶段共用退出／超时分类

- 位置：`orchestrator/project_verifier.py:27–52` 的 `_NATIVE_EXECUTE` 与 `verify_native:230–238`。
- 准备顺序包括 copy source、创建 venv、离线 pip、定位 site-packages 和写 `.pth`，随后才执行真正业务脚本。当前只有 venv／pip 返回非零显式退出 80，被外层分类为 error。
- 正向误分类：复制／定位／写 `.pth` 等准备阶段异常退出 1，会被当业务 failed；整个容器的 wait 从启动计时，若准备阶段用尽资源档案时限，也直接返回 failed 并触发业务修正。
- 反向误分类：整个业务脚本若自然抛出 `SystemExit(80)`，外层同样会当成“离线依赖准备失败”，因为没有独立可信阶段证明区分 80 的来源。
- 建议：用受控准备状态／明确阶段产物记录运行是否真正进入业务脚本，基于阶段和实际退出原因分类；同时区分 Docker IO 超时与确认的业务执行超时。准备失败保持 error，已进入业务后的程序故障保持 failed。
- 验证范围：代码分支可直接确认，尚缺准备阶段卡住、准备异常和业务 exit80 的定点自动反例。无需重跑已通过三仓全套。已即时通知主会话。

#### 10.6 NATIVE-05：超时容器停净前释放了本地验收名额

- 位置：`orchestrator/project_verifier.py:211` 的 `with self._slots` 和 `:256–262` 的 finally。
- 当前 native 版本的 `finally: container.remove(force=True)` 在 `with self._slots` 外；在 wait 超时的 return 路径上，容器仍运行，先退出 semaphore，再进入强制移除。另一验收线程可在前一个容器尚未停止时启动，实际容器数短暂超过配置 2。若 remove 抛错又被吞掉，遗留容器继续占资源，后续仍能再取得名额。
- 对照：旧 `verify` 的清理 finally 位于 `with self._slots` 内；这不是要求随意改变整个旧清理约定，而是新原生执行生命周期比名额生命周期长。
- 建议：本地验收名额覆盖真实停止／移除确认；收口异常留可定位的容器身份与 error，不在仍有进程时声称验收资源已释放。定点 mock 用阻塞 remove 验证“第二次新建不能越过清理”，再覆盖清理失败，不需要跑昂贵内容集合。
- 验证范围：由 Python with/finally 退出顺序确认，未故意制造真实 Docker 清理故障。已即时通知主会话。

#### 10.7 其它未覆盖边界与文档增量

- `_conversation(task_id)` 只冻结当前任务的已消费输入／历史回答，没有显式装入 `requires.artifact='answer'` 指向前一任务的回答。现有两个依赖任务首问大体自包含，尚未证明它们因此失败；但“前一任务回答作为必要输入”的一般契约仍缺评审上下文对账。建议加入真正依赖前答的夹具，确定需要的冻结祖先产物范围，不把整个候选 session 原样复制给评审。
- 生产适配器 wrapper 的细节证据写 `/work/regression-evidence`，位于容器 tmpfs，finally 删除后只剩返回 JSON／摘要／有界 stdout tail 被写进 job。当前不应声称原始 JUnit、各 worker 节点文件和完整 stdout 已持久保留；若交付需要这些原始证据，应增加受控导出与清单，而非引用已删除路径。
- 调查期间 `scripts/validate-project-scenarios.py` 已新增并使用真实 `ProjectVerifier.verify_native`。此前第 7.6 节“未找到正式 CLI”的旧状态在本次增量中撤回；README 可写这个已存在的入口及参数，不再保留不存在的占位指引。未在本次重复执行该 CLI。
- 正式 native spec 内 PS 的 `draft_status/not_executed` 仍是来源元数据；本次主会话已提供实际适配器运行证据，最终文档应以精确项目／task／模式证据同步，不因为通用变量名 draft 就重跑全套。
- 本次没有发现控制脚本从候选目录读取、挂载遗漏只读标志、或工程业务失败被同模型 pass 直接覆盖的明确问题；该结论限上述正常产品路径，不是完整容器安全审计。

## Caveats / Not Found

- 产品文件由主会话并行修改，行号与摘要可能继续变化；本报告不是最终 Check-All。尤其完整对话和原生回归接线在调查期间已出现新增实现，不能沿用先前“尚未实现”的总结当当前缺陷。
- 本研究未执行 Docker 完整构建、模型调用、浏览器、API/DB 跨层、Git、提交或部署。打包 `.env` 缺陷有真实文件及摘要反证，不能写成已经进行过完整发布构建的失败日志。
- 依研究角色隔离协议，未加载 implement/check JSONL；读取了工作流、相关规范、PRD／design／implement／brief 和上述真实定义。所有写入仅本文件。
- 88 个 wheel 的来源与许可汇总、最终 Git 纳入范围和跨平台可用性未在本次只读任务核验。当前制品主要为 linux/amd64 CPython 3.12，不能对其他平台作可运行承诺。
- 本报告没有声称全部 AC 已满足；仍以主会话实际集成测试、Check-All 和最终证据为准。

## 增量研究：project-iterations.md 最小 code-spec 同步草案

- Query: 按当前代码提供六节可采纳增补，并精确列出旧规范中需要限定为 legacy／改写的表述。
- Scope: internal；仅本研究草案，不修改 `.trellis/spec/` 或产品，不运行昂贵测试。
- Date: 2026-10-21
- 目标文件：`.trellis/spec/vibecoding-bench/backend/project-iterations.md`。下列为待主会话采纳的文本；前面两轮发现按其调查时状态保留，本轮不把已经修复的缺口再写成当前实现。

### 原规范最小改写清单

建议保留原有六节历史契约，给第一个 Scenario 标题加明确版本限定，再新增下方六节。两个 schema 必须分名：**内容 schema 1／2** 与 **执行 policy 无 schema／2／3**，不能继续仅写一个含混的“schema 2”。

| 原文精确匹配／位置 | 最小改写或限定 |
| --- | --- |
| 标题 `## Scenario: 冻结内容、持久实例与自动业务验收` | 改为 `## Scenario: legacy 内容 schema 1 的线性步骤与计划执行`；开头声明本节的单步与同 CLI 多步分别指无 schema policy／policy 2，共享停止／鉴权／文件交接规则继续适用新版本。 |
| API 行 `API 总是创建 schema 2` | 改为“根据冻结内容分流：内容 schema 1 创建 policy 2，内容 schema 2 创建 policy 3；服务端归一策略，调用方不直接指定 schema”。 |
| `ProjectIterationManager.create_batch(account_id, name, project_keys=None, policy=None)` | 增补实际参数 `scenario_entries=None`；`policy=None` 仅对旧内容维持旧单步兼容，新内容仍走 policy 3 默认。 |
| `**内容与版本**：project_library/catalog.json 为 schema 1` 与 `当前适配协议固定为 python3 app.py` | 将整段首句限定“legacy 内容 schema 1”；新正式目录 schema 2、原生离线入口见新增节，不能写成所有内容仍仅支持 app.py。 |
| `catalog 保留为空` | 改为“旧生成内容保持退役；当前正式 catalog 为 schema 2，三个真实项目共13场景／20任务。源码变更与部署状态分别报告，不删除历史发布／实例”。 |
| `schema 2 一个计划固定 session、cwd...正常同一 CLI 进程和 tmux 逐步交接` | 精确限定为“policy 2 的 legacy 计划”；policy 3 是场景独立候选 session、逻辑任务计划与逐回复严格释放评审，不能宣称相同进程跨评审复用。 |
| `schema 2 由 driver...才封存并独立验收`、`最后一步通过仍须等该 Run 严格释放才收口` | 本段保留为 policy 2；新增 policy 3 单独规定“封存waiting_release→候选严格释放→机械验收／评审→评审严格释放→接受”。 |
| `默认 30 秒，内存 256 MiB、PID 64` | 限定为 legacy `ProjectVerifier.verify`；新 `verify_native` 使用冻结环境 business／regression 各自资源，准备阶段独立区分，不能照搬旧值。 |
| `损坏内容只使新模式返回 503` | 改为“当前 catalog／新建准入不可用返回503；历史 reader 仍从原 release 读取，缺失历史对象准确报错；普通题库不受影响”。 |
| 测试行 `当前默认正式根为空，该命令不传 --root 时应拒绝` | 改为“正式根静态校验输出3／13／20；旧临时 schema 1 夹具继续显式 --root；新内容原生校验用 validate-project-scenarios.py，旧 --all 不用于 schema 2”。 |
| 研究SOP `目标为100个真实轻量开源项目，每个20个有效迭代`、`原生入口与测试适配尚待开发` | 改为“历史100×20工程路线研究里程碑保留；当前内容池方向为100项目、约600～800场景／约2000任务；本轮首批3仓原生适配已有实现，不以填满配额准入”。 |
| 研究SOP第6步 `确实不足20个有效改进的项目保持候选或换仓` | 改为“按真实场景形成数量可变、独立可验收的稳定任务；不以追问／重试／实现测试拆分凑数。已有20项工程路线保留为来源候选，逐项判断是否适合新场景”。 |
| `只有...20步均有明确交付与验收边界，才计入“研究完成”的100项目标` | 限定为历史100×20里程碑的统计口径；当前新增内容准入另要求来源、固定版本、场景材料、分类验收、离线环境和实际适配证据，不设每项目20任务门槛。 |
| 矩阵 `有效改进不足20步`、`原生测试通过，但 verifier 仍只接受 app.py` | 第一行改为“不足以定义真实场景／独立验收则继续研究，不凑数”；第二行改为“未接入当前受支持原生适配器则平台未就绪”，保留研究与接入的边界。 |
| 错误用法的纠正 `正式目录保留空库状态` | 改为“正式目录只接入实际就绪真实内容；不恢复旧生成项目凑数，临时合成夹具不入正式目录”。 |
| 路线测试 `每项目恰好20个有效步骤` | 限定只用于历史二十项研究文档审计；当前 schema 2 校验可变场景／任务、稳定 ID、真实 DAG 和所有入口／分支可达。 |

下方增补应放在历史线性模式节之后、来源研究 SOP 之前；只保留这六节，不把本研究的发现列表一并复制进规范。

## Scenario: 内容 schema 2 的真实项目多场景任务与 policy 3

### 1. Scope / Trigger

- 修改 `project_scenario_content.py`、`project_scenarios.py`、`project_evaluation.py`、`project_scenario_usage.py`、`project_review_runtime.py`、`project_native_regression.py`、原生验证器、场景 API／页面或正式内容时适用。账号角色、租约、唯一凭据所有者仍遵守 account-runtime-v3；旧线性模式按前节版本读取。
- 当前正式内容为 `real-project-scenarios-v1`，python-frontmatter 4场景／6任务、pydantic-settings 5／7、Typer 4／7，共17个非工程任务和3个工程任务。任务类型固定 `understand/consult/diagnose/plan/modify`，不要求每项目20步。内容就绪、本地模拟机制、真实模型完成及生产部署分别计数。

### 2. Signatures

```python
ProjectIterationManager.create_batch(account_id, name, project_keys=None, policy=None, scenario_entries=None)
initialize_scenario_schema(connection) -> None
normalized_scenario_policy(values, project_count, account_limit) -> dict
ProjectVerifier.verify_native(candidate, project_root, specification, environment_root, profile,
                              *, answer='', regression=False) -> dict
ProjectScenarios.finish_captured_quota(run_id) -> bool
observed_model(directory, response, session_id) -> str
```

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

**发布与状态**：新批次paused且只写元数据，首次实际启动才物化场景独立工作区／候选session。同项目至多一个候选写入；逻辑计划默认2任务、通过5任务或局部收口轮换，活动池默认3，共享并发最多2并受账号真实容量约束。任务通过、代码接受、场景收口与批次运行完成分开；只读任务不会创建代码检查点，completed可包含明确失败／耗尽／受阻。

**代码依赖接受来源**：code依赖必须对应前置task的passed与accepted_checkpoint_digest，并定位该摘要的passed评测作业。`project-artifacts/task-inputs/<task_id>/code-dependency.json` 保存dependencies作业ID→摘要、base_checkpoint_digest、base_checkpoint_job_id及ready／replacing状态。多依赖须沿评测evidence中的 `parent_code_job_id` 属于同一已接受父链；不能用摘要相同折叠回退后的不同分支，更不能猜测合并。工作区非所需版本时先保存原现场，再从已核对对象物化；交接中断受阻。候选evidence冻结 `parent_code_digest,parent_code_job_id,input_checkpoint_digest`；授权范围验收使用该作业冻结输入，不能使用后来变化的任务checkpoint代替。

**严格释放与接受**：真实父链／输入消费／source/generation核对后定向冻结、封存回答和候选，并先持久waiting_release与complete决定。driver正常退出，精确来源严格释放后才排机械验收；需要评审时经原Scheduler／normal额度和共享CLI租约创建project_review，候选不持名额等待评审。评审结果封存后也须严格释放，CAS核对父generation／状态、最新作业及未收口执行后才接受或披露／有限修正。重复候选／评审通知重放已落决定，不重复freeze；迟到旧代结果不推进。完整输出遇quota／重启只续验收，不再重问；旧Run终态保留。

**同实际模型评审**：场景冻结原账号身份、CLI版本、effort和配置execution_model（空串也是合法配置快照）。候选封存时从已核对主assistant精确原生位置读取 `message.model`，存evidence `resolved_model`；私有评审用该值作 `CLAUDE_MODEL_OVERRIDE`，评审结果再核实际原生模型完全一致。禁止因CLI默认／全局设置变化静默换模型，也不调用模型清单探测。评审使用独立session／PID／mount／HOME／input／日志，原账号netns、AT-only副本和唯一刷新所有者；候选无法从其共享目录读取隐藏材料。资源从原账号静态预留512MiB单评审池，旧已创建环境缺匹配layout时明确拒绝并要求空闲重建，不超分账号预算。

评审包冻结完整已消费当前任务对话、回答、rubric、真实源码事实、程序结果及实际交付candidate_files（逐对象摘要核对），总上限512KiB，超限受阻不截断。输出最多64KiB的单JSON，身份字段为 `job_id/task_id/turn_no/response_digest/basis_digest`；decision限disclose/pass/fail/uncertain，逐criterion恰好一次，证据必须在冻结清单且candidate引用获显式许可，反馈限白名单。程序失败不能被语义覆盖；合法uncertain直接受阻，不重抽。modify仅在native及适用regression通过后接受；声明semantic的交付要求还须评审。

**预算与恢复**：policy3候选 `timeout_sec=600`、`task_budget_sec=1800`；业务首轮加最多2次继续／修正，实际输入消费才扣，正常澄清与额度接续不增业务尝试。`review_timeout_sec=180` 限同一逻辑评审跨Run/source累计；同回答最多首次＋1次错误重评且回答总上限为其2倍；`review_budget_sec=720` 限任务全部回答轮次累计。单次领取三层剩余量最小值，infra恢复对业务任务／冻结回答各最多2次，不重置余额。候选及任务累计、任务review累计公开范围60～86400秒；review单次60～600；实际剩余不足公开最小值也不能向上补发。boot＋monotonic片段启动前预留，退出按真实高水位结算，尾段不明保留预留且受阻，不伪造耗时或清零。token按精确source字节区间、session/message去重，统计complete与任务passed不同。

**原生验证**：`verify_native` 在同批account镜像、UID1000／network none／只读根／无账号凭据内执行；源码、baseline、offline、控制脚本与输入只读，临时运行树隔离。离线准备阶段证明与业务时限分开；环境error只本地有限重试，不投递业务修正。工程回归从固定baseline恢复上游适用集合，核Python／插件／baseline与节点contract，业务通过后真实执行，不只检查声明或退出码0。新原生验证的并发名额覆盖容器清理；清理无法确认时保留阻断记录。内容复制、Docker忽略与源码快照须一致；Typer上游公开.env仅按精确固定路径／摘要保留，不放开其他环境文件。

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
| 评审实际模型不一致／格式或身份错误 | 评审error，最多一次错误重评，不算业务失败；合法uncertain直接blocked。 |
| 次数或累计预算先到上限 | exhausted／最终failed或评测blocked，独立任务继续，真实后继依赖受阻。 |
| 停止、旧generation、非最新作业迟到结果 | 留历史不接受；认证／真正严格清理失败沿原强门禁阻断批次。 |
| artifact跨实例、非清单path、对象摘要不符 | 拒绝读取或接受，不回退到当前目录；预览最多65536字节。 |

### 5. Scenarios and Examples

- 正常：创建 `{"account_id":1,"project_keys":["python-frontmatter"],"scenario_entries":{"python-frontmatter":{"FM-S02":"diagnose_only"}}}`，服务端生成policy3和600秒默认；只选择该入口任务集合。正确无BUG／信息不足／方案可通过而不增加代码checkpoint。
- 恢复：前两任务passed、第三任务半途timeout时，旧Run保持timeout，新Run复用第三任务session与半成品，消耗原剩余任务预算；若回答已封存则只续原验收，不新建一次业务询问。
- 代码依赖边界：A接受为作业10、B接受为作业11；以后另一作业把源码回退成A相同字节，不能因此声称B与该回退分支有共同接受父链。使用parent_code_job_id逐作业追溯，无共同链则受阻。
- 错误用法：配置execution_model为空便让评审使用当前全局默认，或给review另开供应商调用；正确做法是沿原Scheduler，冻结候选实际message.model并在review原生日志再次核对。
- 错误用法：CLI success、问答passed或批次completed都算代码成功；正确做法是分别显示执行、任务、代码接受及收口分布。固定测试／模拟CLI通过不计真实模型完成数。

### 6. Tests Required

- 内容／历史／DTO：`test_project_scenario_content.py` 覆盖可变任务、非紧邻DAG、入口可达、隐藏投影、wheel损坏／链接、注册复开摘要、坏catalog历史可读、新600／旧1800默认及显式值／非法null；旧schema夹具回归保留。
- 状态／恢复／父链：`test_project_scenarios.py` 覆盖实际消费认领、澄清不加attempt、3次上限、工作高水位／崩溃预留、review三层预算、候选与review严格释放、完整输出quota／重启只续验收、迟到结果、文件交付进review包、局部轮换／分支激活、代码依赖恢复与不兼容／相同字节回退分支、实际模型漂移不扣业务修正。
- 协议／用量／私有运行：`test_project_evaluation.py` 覆盖严格单JSON／错误身份／重复项／未知证据／程序失败不能被pass覆盖、合法uncertain、显式candidate证据许可及缓存字段去重／未知；`test_project_review_runtime.py` 覆盖owner刷新身份、创建／停净／缺失／孤儿、清理失败保留holder及资源份额；`test_project_native_verifier.py` 覆盖准备阶段error、业务exit80为failed、清理前不放slot、合法等价程序提取。
- 原生内容：`python3 scripts/validate-project-library.py` 仅静态摘要／3-13-20；`scripts/validate-project-scenarios.py --project <key> --task <key> --image <隔离账号镜像>` 真实业务，按需 `--candidate/--answer/--entry/--branch/--expect failed`；`--regression-only` 或 `--with-regression` 使用独立回归资源。保留三工程原版失败／参考通过、原生完整集合与skip/xfail证据，不用宿主旧基线替代。
- 真实调度与UI：`deploy/v3/run_local_verification.py --manifest <隔离清单> --project-scenarios-only --scenario-capacity 1`，另测容量2；需要UI与失败恢复时加现有 `--scenario-browser`／`--scenario-failures`。核原Scheduler／driver／SQLite、holder容量、私有挂载与AT-only、超时半成品、仅续验收及页面状态／预算／用量对账；模拟CLI证据明确real_model_calls=0。旧project-iterations／project-scheduling、quota／window及普通题库适用回归继续保留。

### 草案依据与限制

- 主要依据：`project_scenarios.py` 的九表、`_bind_code_dependencies/capture_submission/_conversation/_mechanical_job/_package/_capture_review/_apply_result/budget`，`project_scenario_usage.observed_model`，`project_review_runtime.start_run`，当前main DTO／nested路由与 `project_verifier.verify_native`；均读取实际定义，不新增虚构字段。代码继续并行变更，主会话采纳前按当前函数定位复核。
- 本轮仅查询测试函数与可运行入口，没有重跑昂贵测试；“Tests Required”是断言要求，不能当本研究宣称测试通过。新code-spec不包含生产已部署或真实模型质量已校准的承诺。
- 旧规范对真实来源、固定commit、许可、原生取证、历史保留及临时合成夹具的原则仍有效；只调整当前事实与计数口径，不删除既有100×20研究事实或历史结果。

## 增量研究：待采纳规范提案的定向事实核对

- Query: 核对 `.deploy/project-scenario-workflows/spec-proposal/` 三份提案的新增事实，重点默认600、无显式code依赖任务输入、同task不reset与owner superseded；不执行Check-All。
- Scope: internal；只读提案与当前产品，仅追加本研究文件，不跑昂贵测试。
- Date: 2026-10-21

### 必要纠错

`spec-proposal/project-iterations.md:222` 的“旧身份、环境或已替换AT的请求不阻新准入”中，**“已替换AT”需限定为原所有者已发布不同且未过期的有效AT**。`project_review_runtime.py:_refresh_applies` 只有在profile中的accessToken非空、expiresAt为数值且大于当前毫秒时间、token摘要与rejected_access_digest不同这三者成立时，才将旧请求视为不再适用。替换成已过期／缺有效期的不同AT仍保留当前待办门禁，不能按现有宽泛措辞推断必定放行。

建议只将该句改为：“待办字段为request_id、identity、environment_id、environment_generation及rejected_access_digest。旧身份／环境代次的请求，或原所有者已发布不同且未过期AT后不再适用的请求，不阻新准入；新请求才把旧记录归档为superseded并保留previous_status。”其余刷新owner锁／request_id CAS／error门禁表述与当前实现相符。

### 定向核对结论

- 未发现提案签名、九表名称及预算值不符；API使用exclude_unset，schema2内容归一默认timeout_sec=600，旧DTO声明1800不覆盖它。
- `project_scenarios._bind_code_dependencies` 当前对所有新task绑定确定base；无显式code依赖时先定位场景已接受checkpoint，尚无接受作业则使用seed及已有entry-inputs冻结snapshot；同task已存在state=ready的code-dependency标记时核对后直接返回，保留当前半成品，不reset。提案:214的表述与此相符；task／entry／branch输入分别由持久物化标记保证幂等。
- code父链确实按接受评测作业ID追溯parent_code_job_id，不以相同源码摘要连接不同回退分支；候选evidence冻结输入checkpoint及父code作业。未发现提案将该身份虚构为独立数据库列。
- account-runtime-v3新增布局行与backend-index条目未发现需要纠正的事实。上述“相符”仅限本次定向检查，不代表整份规范、实现或Check-All已通过。
