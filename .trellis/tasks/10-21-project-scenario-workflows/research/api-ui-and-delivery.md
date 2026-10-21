# Research: 多场景任务的 API、页面与交付边界

- Query: 项目迭代改为业务场景及多类型任务后，真实 API、页面状态、累计成本、恢复交互与历史兼容需要改变什么；人工审核和独立模型评审分别带来什么交互要求。
- Scope: internal
- Date: 2026-10-21

## Findings

### 1. 研究范围与结论

本研究读取了本任务 `prd.md`、`research/project-scenarios/README.md`、`.trellis/workflow.md`、相关前后端规范及下列代码。仅研究跨层公开边界，不定义最终内容 manifest，不修改调度器，也没有运行模型、测试基线或本地验证栈。

现有实现可复用项目入口、账号共享容量、批次控制、Run 日志入口、历史对象预览和 SSE 生命周期。需要重新定义的是公开的场景／任务进度、不同结果的语义、回答证据、任务预算及评审结果；只把“步骤”改名为“任务”无法满足本次要求。

### 2. 已找到的文件

| 文件 | 当前职责 |
| --- | --- |
| `orchestrator/main.py:10136` | `ProjectIterationBatchIn` 请求 DTO、项目目录／批次／实例／成果／用量／SSE 路由 |
| `orchestrator/main.py:7825` | 服务启动时把当前内容库与项目管理器一起初始化 |
| `orchestrator/project_iteration.py:123` | 目录、批次、实例的公开响应和状态动作 |
| `orchestrator/project_iteration.py:455` | 逐原生消息去重与独立尝试字节边界的现有用量计算 |
| `orchestrator/project_iteration.py:891` | 从固定对象读取验收成果及历史文件，避免使用当前目录冒充历史 |
| `orchestrator/project_library.py:192` | 目录的公开字段投影，隐藏验证及参考内容 |
| `orchestrator/project_plans.py:175` | 公开计划范围、完成步数及关联 Run，不公开原生 session／进程证明 |
| `webui/app.js:55` | 项目页面所有加载、渲染、状态映射、控制动作和 SSE |
| `webui/index.html:69` | 项目页模板及创建批次表单 |
| `webui/style.css:1591` | 项目页布局、长列表、报告预览和窄屏规则 |
| `cc2api/src/service/runtime_bridge.rs:152` | `/runtime` 管理桥的资源白名单和方法边界 |
| `orchestrator/test_project_iterations.py:397` | 项目 API 鉴权、DTO 类型、旧入口拒绝和不可变历史等回归 |
| `orchestrator/test_project_plans.py:146` | 严格策略、恢复、输入消费、迁移及停止竞争等回归 |
| `scripts/validate-project-library.py:17` | 原 JSON 行协议的内容／参考行为校验，不是新真实项目校验器 |
| `deploy/v3/verify_project_browser.py:14` | 真实页面→API→SQLite 的合成数据检查 |
| `deploy/v3/run_local_verification.py:17` | 随机标签的本地隔离 Docker 执行／调度验证入口 |
| `deploy/v3/verify_stack.py:53` | 独立管理栈及浏览器验证入口 |
| `images/v3/Dockerfile:35` | 把正式内容库复制到 control 镜像 |
| `images/v3/Dockerfile.dockerignore:29` | 正式内容库的构建上下文放行项 |
| `deploy/v3/manage.py:215` | 源码快照列表已包括 orchestrator、webui 和 project_library |

### 3. 真实的现有接口与缺口

#### 3.1 创建请求只有工程计划策略

`ProjectIterationBatchIn` 的实际字段为：

- `account_id: StrictInt`；`name: StrictStr = "项目迭代批次"`；`project_keys: Optional[list[StrictStr]] = None`。
- `concurrency: Optional[StrictInt] = None`。
- `active_projects: StrictInt = 3`；`rotation_steps: StrictInt = 5`；`steps_per_plan: StrictInt = 2`。
- `timeout_sec: StrictInt = 1800`；`interval_min_sec: StrictInt = 0`；`interval_max_sec: StrictInt = 0`。
- `model_config = ConfigDict(extra="forbid")`，不能由前端直接附加任意新字段。（`orchestrator/main.py:10136`）

创建路由用 `body.model_dump(exclude={"account_id", "name", "project_keys"}, exclude_none=True)` 整理策略，然后调用 `create_batch`；新 API 当前总是走 schema 2 策略。管理器仍用选中项目 `len(manifest['steps'])` 的最大值验证计划步数，内部 `policy=None` 才保留旧模式。（`orchestrator/main.py:10189`、`orchestrator/project_iteration.py:132`）

新模式若需要由批次设置任务累计预算、评审模式或执行范围，需要在 DTO、策略归一、持久化与表单同时定义；也可以由冻结内容或执行配置提供部分值。具体归属尚未确定，本文不把拟议字段当成现存 API。

`timeout_sec` 现指单次 CLI 计划的工作超时，不能悄悄改成跨恢复的单任务总预算。旧批次语义须保留，新预算必须有单独明确的版本语义和单位。

#### 3.2 公开读取按步骤投影

| 路由 | 现存结果 | 新能力需要的公开语义 |
| --- | --- | --- |
| `GET /api/project-catalog` | `version,digest,scheduling_defaults,projects`；项目含 `project_key,title,category,source_topic_no,description,seed_digest,step_count,milestones` | 按版本公布场景数、可执行任务数、类型覆盖与接入就绪情况；研究数量不能当成可执行数量 |
| `GET /api/project-catalog/{key}` | 上述摘要加 `steps[{id,goal,milestone,requires}]` | 公开业务场景、用户目标、允许修改范围、实际依赖；不返回隐藏参考、评审依据或尚不应披露的材料 |
| `GET /api/project-iteration-batches[/{bid}]` | 批次 `policy,counts,scheduling`；详情另含 `instances` | 批次运行生命周期与结果统计分开；终止运行可含失败／受限任务，不能把“所有项目通过”作为唯一收口形式 |
| `GET /api/project-instances/{iid}` | 实例 `next_step_index,step_count,steps,milestones,attempts,plans` 等 | 每场景／任务独立状态与结果、原因及必要依赖，单独提供代码接受状态；分支不执行与前置受阻不能混为失败 |
| `GET /api/project-instances/{iid}/usage` | 按 `step_id` 累计 `tokens_in,tokens_out,requests,attempts,known_attempts,complete` | 按任务及类型累计完整尝试与恢复成本，区分执行用量和评审用量，并能判断缺失证据 |
| `GET /api/project-step-attempts/{aid}/artifacts` | `attempt_id,validation_status,report,files`；有快照时另有 `digest,changes` | 问答也需可固定的回答／证据／审核版本；没有代码产物不等于没有交付；报告与代码检查点接受分别表达 |
| `GET /api/project-step-attempts/{aid}/file?path=...` | 只读固定对象的有界文本，最多预览 65,536 字节 | 保留既有快照完整性和路径边界；问答报告不能拿当前 transcript 或可变工作目录替代已审核版本 |
| `GET /api/project-iterations-stream` | 每两秒 `project-state` 事件，内容为 `batches` 及按所选 ID 附加 `batch,instance` | 与普通读取使用同一公开投影和统计；新状态、预算与结果不能只出现在某一个读取入口 |

证据：`orchestrator/main.py:10174`、`:10239`、`:10248`、`:10277`、`:10286`、`:10316`；`orchestrator/project_library.py:192`；`orchestrator/project_iteration.py:175`、`:203`、`:220`、`:891`；`orchestrator/project_plans.py:175`。

现有批次 `counts` 是 `project_instances.status` 的分组计数，不是任务结果计数；现有 `completed_steps` 是线性范围的通过数，不能推导含分支的任务清单。新接口不应仅依赖客户端从 `next_step_index` 猜测前面全部成功。

#### 3.3 现存写动作不包含评审或材料补充

当前公开项目写动作仅创建批次及 `start/pause/stop`。`start` 仅允许 `paused/pausing/active`，已停止、阻塞或完成批次拒绝重开。（`orchestrator/main.py:10189`、`:10221`；`orchestrator/project_iteration.py:230`）

本次若要让人补充场景材料、审核回答或手动确认恢复，均需要新增受控动作及严格输入 DTO；不能复用 `start` 令一个仍缺材料、预算耗尽或证据损坏的任务自动通过门禁。动作须绑定准确的任务／尝试／回答或候选版本，拒绝陈旧或重复决定，避免一次审核误作用于后来重新生成的回答。具体路径应在设计阶段确定。

### 4. 页面真实行为与改造位置

#### 4.1 目录、批次表单与项目统计

`renderProjects()` 把账号、目录、历史批次放在同一个 `Promise.all` 内，任一失败就显示错误并禁用整个表单。（`webui/app.js:108`）目录标题和选择卡按 `step_count` 显示，预览仅列 `steps[].goal`，还会截掉 `Interface contract:` 后缀。（`:117`、`:124`、`:159`、`:166`）新模式需要按版本显示场景与任务；内容研究说明、可执行内容、真实模型结果应保持区分。

表单的 `rotation_steps`、`steps_per_plan` 当前按选中项目的最大 `step_count` 设置 `max`，提交时七项策略统一 `Number(...)`。（`webui/app.js:88`、`:188`；`webui/index.html:89`）真实依赖与条件分支下，最大清单长度并不能证明一个计划可以连续投放多少任务。轮换按任务通过数、已执行数还是场景收尾计算，必须先确定，再同步 DTO、调度策略及文案。

#### 4.2 当前状态映射会混淆新结果

`projectStatus()` 同时处理批次、实例、计划、Run、验收多个状态域，`completed` 统一变为“路线完成”，`passed` 为“验收通过”，`success` 为“执行结束”，`timeout` 仅为“超时”；未知值会原样显示。`projectStatusPill()` 将 `blocked/error` 一起映成失败颜色。（`webui/app.js:61`、`:75`）

建议新响应明确多个状态域，页面按所属对象翻译，不再用一个 `completed` 文案解释所有对象。至少必须分清下列情况；下列中文是语义需求，不是已经存在的后端枚举：

| 页面需要表达的事实 | 结果／动作边界 |
| --- | --- |
| 回答或修改已交付，等待独立验收／审核 | 不是任务通过，也不应要求再生成同一答案 |
| 任务通过，代码无变更或不需要接受 | 可推进问答结果，不能增加工程能力数或新的代码检查点 |
| 工程行为通过且候选已接受 | 标明被接受的候选／代码版本，后续依赖才能使用 |
| 执行超时但任务尚可继续 | 旧 Run 保留 timeout；页面展示剩余任务预算、尝试次数及是否允许恢复 |
| 当前目标需要补充信息 | 展示具体缺少材料及当前可披露材料；“合理指出缺什么”已满足窄任务时可独立通过，不能一律挂起 |
| 次数或累计运行预算耗尽 | 有明确未完成结果，自动继续结束；不能恢复后重置额度 |
| 前置未通过或缺少已接受代码 | 显示所依赖的实际任务与原因；独立任务仍能运行 |
| 会话／输入消费／候选证据不可靠 | 保留现场并受阻；不能提供无条件“重试”按钮 |
| 验收基础设施异常 | 独立于业务错误，不诱导模型重复修正正确结果 |
| 当前运行全部收口 | 展示通过／失败／耗尽／受阻等分布；不统一显示“全部路线完成” |

批次调度提示已按 active、paused、pausing、stopping、stopped、blocked、completed 分支显示，并只在 active 且将来时间显示下一投放；这个区分应保留。（`webui/app.js:268`）

#### 4.3 实例页须从线性路线转为场景和任务

当前实例页用 `next_step_index / step_count` 表示“已验收”，用 `index < next_step_index` 给路线打勾，计划提示把“下一步”算成 `start_index + completed_steps + 1`。（`webui/app.js:328`）这些做法不适用于任务依赖图、可跳过分支及独立场景。

实例页建议分为场景清单、任务结果、执行／恢复记录、代码版本和成本视图。场景展开后展示任务类型、用户目标、结果及依据；尝试与 Run 仍留可追溯链接。当前执行／验收双列可复用，但新任务结果、代码接受不能压缩进其中任意一列。

成果弹窗当前标题“验收与版本”，正文是原始 JSON 报告与固定文件清单；问答需要展示被冻结的回答、适用源码版本、关键证据、评审结论和理由，文件快照作为可选部分。（`webui/app.js:369`）这些内容必须来自服务端固定证据，不能以最后一次可变回复覆盖旧审核结果。

#### 4.4 运行页保留项目恢复的唯一入口

运行页已对 `run_kind === 'project_iteration'` 隐藏普通“继续”按钮；后端 `POST /api/runs/{rid}/continue/start` 同样对该类运行返回 409，普通 task 再运行也被拒绝。（`webui/app.js:2650`；`orchestrator/main.py:11362`、`:10864`）

新问答需要多轮不代表可以放开普通 Run 续聊，否则会绕过材料披露、预算和任务结果记录。应由项目任务控制链推进。若提供人工恢复按钮，按钮是否可用应由服务端证明状态决定，旧 timeout Run 不改写为 success，新 Run 关联原任务。

#### 4.5 SSE、资源与表单草稿

当前 `connectProjectStream()` 以所选批次及实例订阅，同一 source 才接受回调；切 tab 时 `navigate()` 关闭项目 EventSource。重绘会保留路线展开和列表滚动。（`webui/app.js:245`、`:333`、`:388`、`:427`）这些能力应继续保留。

如果加入审核文本框或补材料表单，不宜放入每两秒会替换的整个 `innerHTML` 区块，否则 SSE 会清空用户输入、焦点或当前审核选择。应让交互草稿与服务端更新的只读区分开，提交绑定准确的待审核对象；重新选择实例时清理旧请求回调，禁止把旧响应绘到新实例。

`.project-table-scroll`、报告区和窄屏布局可复用，新增状态颜色走现有 CSS 变量，在明暗主题及 390px 下验证。页面仍为原生 JS 零构建，不需为这次改造引入前端框架。（`webui/style.css:1618`、`:1634`、`:1639`；frontend 规范）

### 5. 分类累计成本的现状与公开契约

现存 `/usage` 按实例的尝试列表逐项累计，只对 `usage_available` 为真的尝试相加；`complete` 表示每个尝试都取得了记录，不代表任务完成。所有尝试都未知时，token 与请求显示 `null`；只有部分已知时返回已知小计，同时 `complete=false`。（`orchestrator/main.py:10248`）

用量底层对独立尝试字节边界内主 assistant 消息按 ID 去重，缺边界、截断或不可信位置直接未知；不会退回整个项目历史计费。（`orchestrator/project_iteration.py:455`、`:513`）新累计统计必须沿用此边界，不能把一个共享 Run 的整段总量复制到每个任务。

`_usage_input_tokens()` 目前把普通输入、cache 写入和 cache 读取相加为一个 `tokens_in`；`native_usage()` 对外只返回这项合计、输出和请求数。页面又只展示请求和输出 token。（`orchestrator/main.py:323`；`orchestrator/project_iteration.py:507`；`webui/app.js:355`）所以“按输入、缓存、输出分类”的要求需要底层保留并公开分项，不能仅从现有合计倒推。

新统计的最小语义包括：

1. 稳定任务及类型归属；澄清、补充材料、失败修正和超时恢复仍属于同一个任务。
2. 每次执行用量及累计去重依据；恢复不重复累计已封存片段。
3. 输入、输出、缓存读／写分项的可用性；未知不是零，不用字符数伪造 token。
4. 累计有效运行时间和剩余预算；现有 `created_at/ended_at` 或 Run 总墙钟时间不能直接视为它，必须扣除预算定义排除的等待，具体核算由运行时设计确定。
5. 业务执行与额外评审分开；若没有冻结价格与真实计费依据，不展示虚构金额。
6. 类型汇总及样本量；类型占比、跨项目权重在比较前固定，不能由任务数自然充当业务流量权重。

### 6. 人工审核和独立模型评审的不同交互

在 `orchestrator/`、`webui/`、`deploy/v3/` 的 Python／JS／HTML／Rust 文件中检索 `judge/rubric/评审/评分/人工审核/manual_review/review_status/answer...eval`，未找到可复用的项目问答评分、人工审核 DTO 或界面。现有自动验收是程序行为，不能当成已有的问答评审器。此结论限于上述已检索目录和入口。

| 项目 | 人工审核首版 | 自动独立模型评审首版 |
| --- | --- | --- |
| 回答交付后 | 进入待审核队列，模型执行已收口，待人判断 | 进入评审排队／执行状态，受评模型执行已经收口 |
| 新交互 | 审核详情、通过／不通过及理由、必要事实证据；审核者提交绑定回答版本 | 展示评审器版本、结论、理由、异常及用量；是否允许人工复核需另行决定 |
| 自动推进 | 依赖回答通过的任务等待审核；独立场景是否继续由调度策略确定 | 评审通过后可自动推进；超时、解析失败或评审不可用不能直接判受评模型错误 |
| 成本 | 保留模型执行成本；人工时间是否记录为运营指标待定 | 额外调用单列评审用量、时间及预算；不能混入受评模型成本 |
| 结果冻结 | 审核决定、理由、审核对象与依据版本留档；重复提交、陈旧提交必须拒绝或幂等收口 | 固定评审指令、依据、模型配置与版本；重评策略不能默默覆盖历史结论 |
| 验证重点 | 审核竞争、重启待审核恢复、陈旧决定、错误回答不能人工误投到下一次回答 | 评审协议异常、停止／重启、陈旧回包、独立用量和错误结论对照样本 |

两种方式都需要先做固定事实、可运行用法和工程行为验收；人工或模型评审不能替代可确定的程序验证。选哪一种是未决产品问题，本文不替用户决定。还需明确是否有评审不确定／材料不足结果、谁可终结这种状态，以及能否在首版手工覆盖自动结论。

### 7. 历史、旧题库及管理桥的硬约束

#### 7.1 历史读取应脱离当前库准入

服务启动把 `ProjectLibrary(PROJECT_LIBRARY_DIR)` 成功作为管理器初始化前提，失败只设置 `project_iteration_error`；所有项目 API 都先取 `_project_manager()`，管理器为空便 503。（`orchestrator/main.py:7843`、`:10164`）项目 Run 文件树也单独要求管理器存在，否则 503。（`:11057`）

因此“旧发布文件和数据库没删除”并不能证明历史批次在当前空库下可读。改造若承诺历史继续可查看，应把当前内容目录／新建能力与历史批次、冻结 manifest、报告／对象读取解耦；页面也不能把目录错误与历史批次读取绑成一个失败面。历史内容缺少对象时要显示真实缺失，不能回退到当前工作区。

#### 7.2 旧版本语义保留

- 已有批次保存 `catalog_release_id`、`policy_json`、实例 `manifest_json` 及固定摘要；新模式不能把旧记录按新任务语义重解释。（`orchestrator/project_iteration.py:163`）
- 旧 schema 1 单步 Run 和 schema 2 多步计划／恢复都已有行为；新内容版本与策略版本是不同边界，不应只增加一个全局版本数字就覆盖两者。具体版本号尚未决定。
- 旧 `next_step_index`、步骤通过、已接受检查点及 `source_topic_no` 为旧记录服务；新只读任务不能借用它们伪造工程能力提升。
- 新迁移要保留 ID、索引、自增序列及旧结果；已有迁移测试已经检查重复初始化和旧行不丢失。（`orchestrator/test_project_plans.py:752`）
- 正式旧生成内容已退役；测试需要时继续使用临时合成目录，不能为满足旧的 100／20 校验而恢复正式生成内容。（`orchestrator/test_project_iterations.py:458`）

#### 7.3 普通题库保持独立

`TaskIn`、`BatchIn` 为普通题库的现有请求对象，紧接在项目 API 后，具有自己的 topic、prompt 和运行参数；不应为新项目场景修改其默认语义。（`orchestrator/main.py:10325`）新模式损坏不能影响旧题库创建及执行，项目关联 `runs.run_kind='project_iteration'` 的入口限制继续生效。

#### 7.4 管理桥按真实资源前缀放行

`browser_path_allowed()` 对 API 按第一个资源段放行 GET／POST／PUT／DELETE，目前项目相关资源是 `project-catalog`、`project-iteration-batches`、`project-instances`、`project-step-attempts`、`project-iterations-stream`。（`cc2api/src/service/runtime_bridge.rs:177`）

新增动作如果挂在现有资源前缀下，会自动满足管理桥资源条件，仍须由 FastAPI 路由／鉴权和 DTO 控制具体动作；如果新增 `project-tasks` 等顶层资源，必须同步白名单及断言。桥本身不做新 DTO 字段校验，不能把桥白名单当业务授权。不要为了新增评审放开 `/internal/*` 或 auth 豁免；现有编码和点段拒绝继续保留。（`:152`、`:205`、`:356`）

### 8. 可独立验证的交付拆分

下表是供主会话组织实现计划的候选拆分，不是已获实现批准的任务清单；具体字段与责任由主设计收敛。

| 交付 | 可审阅结果 | 独立完成标准 |
| --- | --- | --- |
| A. 版本化公开契约和历史读取 | API 投影、严格请求 DTO、旧版本分支及历史读取能力 | 当前库为空／损坏仍可读取真实存在的旧批次和固定成果；新建明确不可用；旧题库正常 |
| B. 多场景结果和预算联通 | 调度端确定的任务／场景状态、依赖、预算、回答及代码接受证据，通过 API／SSE 同步 | 回答通过不产生新代码能力；前置耗尽只阻塞真实依赖；旧 timeout 保留；重启后状态一致 |
| C. 分类验收与所选评审路径 | 可确定用例、固定回答／候选、人工动作或独立评审适配 | 正确回答、错误事实、合理澄清、无 BUG、方案多解及工程候选分别按冻结条件验收；旧回包不能覆盖新状态 |
| D. 项目页及运行页衔接 | 目录统计、场景／任务视图、恢复／审核、成本和固定证据 | 页面能看出任务结果、代码接受与执行结束的区别；多轮不绕过项目控制链；SSE 不丢审核草稿 |
| E. 三项目真实内容准入 | 现有 13 场景／20 任务的真实夹具及验收结果，明确研究／就绪／模型运行状态 | 可变数量实测可用，隐藏依据不进工作区，原生入口和实际加载候选可核对；不以合成 CLI 通过冒充模型能力 |
| F. 兼容、真实链路与打包 | 旧模式回归、API／UI／DB 一致性、镜像与快照路径检查 | 旧 schema 1／2 可解释，普通题库不变，新增必需源码／依赖进入正确构建上下文；本地验证与实际发布分别报告 |

从跨层依赖看，A 与新状态语义需要先冻结；B／C 产出稳定响应后 D 才能完整落地；E 可并行物化，但接入验证依赖 B／C；F 使用各项真实证据收口。不建议先把全部页面改成场景文案再补状态定义。

### 9. 建议检查与现有入口的适用边界

以下仅列推荐检查，本研究未执行。

1. API／状态单元：在 `test_project_iterations.py`、`test_project_plans.py` 或新增同层测试中加入可变任务数、分支、信息待补、待审核、任务通过但代码不变、预算耗尽、依赖受阻、重复及陈旧审核、完整回答只续验收、跨 Run 成本不重复、历史目录不可用仍可读等断言。继续保留认证、清理、输入消费和停止竞争回归。
2. 请求边界：非法 bool／字符串／小数及额外字段应按已冻结 DTO 拒绝；普通 API 读取和 SSE 结果一致；实例必须属于订阅批次的校验继续保留。现有 HTTP 测试位置 `orchestrator/test_project_iterations.py:397`，严格策略测试 `orchestrator/test_project_plans.py:146`。
3. 运行 Python 回归入口可沿用 `PYTHONPATH=orchestrator python3 -m unittest discover -s orchestrator -p 'test_project_*.py'`；具体环境与依赖由实现阶段核对。JS 做语法检查并走实际浏览器，不引入虚构的 npm lint／TS 检查。
4. 管理桥变更执行 `cargo fmt --check` 与 `cargo test --locked`，工作目录 `cc2api/`；资源放行正例与内部／编码路径拒绝反例一起保留。（`.trellis/spec/vibecoding-bench/backend/project-iterations.md:161`）
5. 旧 `scripts/validate-project-library.py --all` 直接执行 `seed/app.py`，加载 `reference_runtime.py` 并要求待开发步骤不在初版通过。（`:24`、`:33`、`:40`）新理解／咨询任务本来就可在基线上完成，不能沿用“基线不得通过”的通用断言；真实项目校验入口必须适配任务类型。不得把真实仓改造成 `app.py` 迎合此脚本。
6. 真实 Docker 执行与调度分别使用现有 `python3 deploy/v3/run_local_verification.py --manifest <清单> --project-iterations-only`、`--project-scheduling-only`。入口为隔离合成数据，不代表实际模型结果；新行为需要补相应场景，不能仅跑旧两步闭环便宣称通过。（`deploy/v3/run_local_verification.py:17`）
7. 浏览器入口为 `python3 deploy/v3/verify_stack.py --manifest <清单> --browser --project-iteration`，要求单独执行。`verify_project_browser.py:45`、`:60`、`:103` 目前硬编码合成 100 项／2,000 步、schema 2 策略和每仓 20 项；应保留为旧兼容夹具，并为新三项目样板／状态补独立夹具，不能把全部旧断言机械替换掉。
8. 新页面验证覆盖真实 API／SQLite 统计、旧与新内容混存读取、空库历史可读、SSE 重绘与切页释放、审核草稿、错误输入、停止与恢复、XSS、1280／390px 和明暗主题。现有浏览器脚本后半会直接准备数据库状态，须继续标明是页面夹具；执行／恢复闭环要由真实 driver 路径另证。（`deploy/v3/verify_project_browser.py:75`、`:122`）
9. 检查新增验收文件和离线依赖的最终落点是否在 control／account 的正确构建上下文与源码快照内；当前已有 `project_library` 打包，不代表未来新目录自然被包含。正式真实内容未就绪时保持明确不可用，不恢复生成项目兜底。

### 10. 相关规范与引用边界

- `.trellis/workflow.md`：研究输出需持久化；当前 planning 不能因创建任务就进入实现。
- `.trellis/spec/vibecoding-bench/frontend/index.md`：原生 JS／HTML／CSS 三文件零构建，项目跨层契约入口。
- `.trellis/spec/vibecoding-bench/frontend/quality-guidelines.md`：HTML 转义、真实表单、错误反馈、重复提交控制、主题变量、SSE 释放与浏览器验收。
- `.trellis/spec/vibecoding-bench/frontend/state-management.md`：单一全局状态、显式 render、SSE 自含数据，不能在每次推送内二次查询。
- `.trellis/spec/vibecoding-bench/frontend/type-safety.md`：Pydantic 请求边界、响应字典为真实契约，数字显式转换，状态新增要同步 UI。
- `.trellis/spec/vibecoding-bench/backend/index.md`：单进程 FastAPI、裸 SQLite 与幂等升级的实际工程边界。
- `.trellis/spec/vibecoding-bench/backend/project-iterations.md:33`：项目 API、字段与版本现状。
- 同文件 `:94`、`:100`、`:110`、`:112`：原生用量边界、禁止盲发、验收／故障分类、管理桥及页面要求。
- 同文件 `:150`：既有本地验证入口及历史兼容回归。
- 同文件 `:163` 起是此前 100×20 研究 SOP；其中固定数量描述是原研究目标，不应继续作为本次新场景数量要求。应由主流程在实现后同步相应规范，不在本研究代理中修改。
- `research/project-scenarios/README.md`：已确认的五种类型、独立任务、自然澄清、代码检查点、验收与成本边界。

外部引用：无。本题只核对本地实现与既有已冻结样板，不引入外部 API、库版本或模型价格假设。

## Caveats / Not Found

- 本文所有“需要／建议”都是设计输入，新增字段、接口和状态尚未实现。现有正式 catalog 仍为空，13 场景／20 任务只是设计样板；没有在本轮运行模型或证明接入完成。
- 已检索的 orchestrator、WebUI、v3 验证目录没有项目问答评审能力；不据此断言整个仓库或外部服务绝对不存在任何通用评测组件。
- 人工审核与自动独立模型评审仍是产品选择；还需确定评审不确定时的收口、是否允许人工覆盖、审核后自动推进，以及额外评审成本预算。研究不替用户选择。
- 还需明确信息补充来自预冻结分支还是允许人工自由追加；后者会改变不同模型可比较的上下文和公平性，不能默默当作同一次标准任务。
- 轮换按通过任务、已收口任务还是完整场景计算，以及场景失败后独立任务继续的具体策略，尚未形成正式契约。
- 累计有效运行时间的计时来源与等待排除，由运行时研究及主设计决定；不能用现有 Run 墙钟时长直接代替。
- 本研究没有对活数据库、生产历史对象或正在运行的环境做读写验证。历史读取失效是由当前初始化和 API 依赖得出的代码结论，不是声称线上已发生故障。
- 未运行任意 git 操作、模型调用、项目原生基线、本地 Docker 验证、提交、推送或部署；只新增本任务研究文件。
