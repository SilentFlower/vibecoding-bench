# 调度、配置与可靠调用候选研究

研究日期：2026-10-21。母任务：`10-21-project-catalog-expansion`；首批实施边界由 `10-21-project-catalog-pilot-pack` 的 planning 产物决定。本文只研究与规划，没有修改上游源码、正式内容库、平台实现或生产数据，没有调用真实模型，也没有重复完整原生基线。

## 结论与候选排序

首批推荐 **schedule，5 个连贯场景、13 个任务**：理解 2、咨询 3、诊断 4、方案 2、修改 2。十一项任务通过回答或方案结束；两项修改分别解决真实的尾部额外等待和默认未配置 Job 的 repr 异常。不强制凑成十二项或二十步。python-dotenv、Tenacity 进入后续 wave。

| 候选 | 官方固定版本与许可 | 本轮核对 | 历史隔离成本，非本轮重跑 | 首批取舍 |
| --- | --- | --- | --- | --- |
| [dbader/schedule](https://github.com/dbader/schedule/tree/82a43db1b938d8fdf60103bd41f329e06c8d3651) | `82a43db1b938d8fdf60103bd41f329e06c8d3651`，1.2.2，MIT；保留 LICENSE.txt 与版权声明 | 本地 HEAD、origin、源码、许可证和官方 commit API 返回完整 SHA 均吻合；工作树干净 | Python 3.12.3，81 项通过，pytest 约 0.62 秒，256 MiB 容器约 1.537 秒；宿主测试峰值约 48.9 MiB | 单产品模块、核心零依赖、无服务，业务假时钟和回调事件可独立验收，最适合首批 |
| [theskumar/python-dotenv](https://github.com/theskumar/python-dotenv/tree/0b2880591780a426b0551436f47a17e7a76d954f) | `0b2880591780a426b0551436f47a17e7a76d954f`，1.2.4，BSD-3-Clause；保留许可与归属 | 本地 HEAD、origin、许可证、DotEnv / Variable.resolve / set_key 定义及官方 commit API 完整 SHA 均吻合；工作树干净 | Python 3.12.3，288 项通过，pytest 2.973 秒，256 MiB 容器约 3.906 秒；约 83.5 MB 测试 venv 含 IPython | 核心零依赖，但全套含 Click、IPython、CLI 入口、权限/FIFO；须隔离祖先 .env，优先级次于 schedule |
| [jd/tenacity](https://github.com/jd/tenacity/tree/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6) | `32ac68f0941319c0d2f4fb927f96e4ee29bb46c6`，Apache-2.0；保留 LICENSE、版权头及适用归属；浅检出动态版本 `0.1.dev1+g32ac68f09` 不是发行号 | 本地 HEAD、origin、许可证、wait / stop / BaseRetrying.wraps 定义及官方 commit API 完整 SHA 均吻合；工作树干净 | Python 3.12.3，185 主项及 15 子测试通过；JUnit 200，不能重复相加；pytest 2.996 秒，256 MiB 容器约 3.863 秒，峰值约 48 MiB | 零运行依赖但完整同步/异步/重入生命周期更复杂；适合第二波可靠调用主题，不在首批增加异步负担 |

官方 API 只核存在的固定提交，未将默认分支的新变化混入冻结版本：`https://api.github.com/repos/<owner>/<repo>/commits/<完整SHA>`。三次返回的 SHA 均精确一致。官方网页抓取器返回 restricted URL，随后通过官方 api.github.com 成功核对，没有采用第三方镜像。

三者历史测试均无网络、无外部服务、无账号 HOME、UID/GID 1000、只读根、删除 capabilities、禁止提权，实际 256 MiB 下没有 OOM，因此相对现有 1536 MiB 业务预算有较大余量；这不是当前正式镜像与新冻结验收已经通过的证明。首次接入仍须测当前固定解释器、离线 wheel、候选导入路径、实际峰值和清理。

## 来源与本轮新增取证

已完整读取三个候选的 `research/github-projects/<项目>.md` 和各自 `*-roadmap-20.md`；路线中的增强只是研究提案，不是上游承诺，不把二十步机械转换为任务。

- schedule 源码与历史证据：`.deploy/real-project-review-20261021/schedule-review/`。
- python-dotenv 源码与历史证据：`.deploy/real-project-review-20261021/python-dotenv-review/`。
- Tenacity 源码与历史证据：`.deploy/github-100-research/core-utils/tenacity/`。
- 三个固定工作树的 `git status --short` 本轮均为空。
- schedule 本轮源码 SHA256：`schedule/__init__.py` = `b0c93f8ee84cbb8dbb98bcb8284864f4ea04012fdbc216de13f8ad2141d09efa`；`test_schedule.py` = `71fa3781959b0dee649acc01e618559792c52c6375b82880945764819d5d5523`；`LICENSE.txt` = `30a8352c318ce1b645acde0299697342d4380ed2637d7ca18a8ad25661e3b41b`。

本轮仅用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<schedule源码> python3 -B` 的短脚本直接导入原版，`unittest.mock.patch` 替换业务模块内 datetime/sleep，并记录真实回调事件。没有导入候选可改测试作为验收工具，没有真实长睡眠。以下输出是本轮实测；完整 81 项仍引用历史证据。

| 最小原版观察 | 本轮结果 | 判断 |
| --- | --- | --- |
| run_all(2)，0 项 | `[]` | 正常反例：空集合不等待 |
| run_all(2)，1 项 | `job0, sleep(2)` | 真实尾部等待，多一次 |
| run_all(2)，3 项 | `job0, sleep(2), job1, sleep(2), job2, sleep(2)` | 真实尾部等待，3 次而应为 2 次 |
| 每分钟任务注册于 12:00，12:30 连续轮询两次 | 回调一次；next_run=`12:31:00` | 原版明确不补跑，不能判 BUG |
| 两分钟任务 12:02 执行，回调把业务时钟推进到 12:02:30 | last_run=`12:02:30`；next_run=`12:04:30` | 原版从回调结束排期，不是固定节奏 |
| 连续 `.at('10:00').at('16:00')` | at_time=`16:00:00` | 单 Job 单时点；可用两个 Job，暂不增强 API |
| `repr(Scheduler().every())` | `TypeError: 'NoneType' object is not subscriptable` | 真实缺陷：interval=1 导致 `unit[:-1]` |
| `repr(Scheduler().every(2))` | `Every 2 None do [None] (last run: [never], next run: [never])` | 正常反例：不能声称所有未配置 Job 都崩溃 |
| `str(Scheduler().every())` | `Job(interval=1, unit=None, do=None, args=(), kwargs={})` | str 已可用，无须修改其语义 |
| run_all 首回调抛 ValueError，次回调健康 | 只记录 failed_job，异常向上传播 | 文档规定，不擅自吞异常 |
| 回调返回 CancelJob，手工 `job.run()` | 返回信号，仍在调度器中，tag 查询 1 项 | 直接 run 不自动消费取消信号 |
| 同一任务经 `scheduler.run_all()` | tag 查询 0 项 | 调度器 `_run_job` 消费取消信号 |
| `.every(0.5).seconds.do(...)` | interval 保留 0.5，正常注册 | 正数小数已支持，不另立“支持小数”任务 |

以上13条观察由同一只读短脚本输出并写入本文；没有为增加计数而把测试对照拆成业务任务。原版0/负间隔有界超时的历史证据仍在 `reproductions-result.json`，本轮没有再启动卡住子进程；不把该第三个修复塞入首批。

## schedule 接入与验收共用约束

固定源码只保留原工程：`schedule/__init__.py`、`test_schedule.py`、docs、MIT 许可证和 pyproject。核心无需第三方运行依赖；覆盖原生时区回归须离线冻结 pytz。历史测试依赖为 pytest 9.1.1、pytz 2026.5、iniconfig 2.3.1、packaging 26.3、pluggy 1.7.0、Pygments 2.21.0；首次适配时校验 wheel/hash/解释器适配，不临时联网安装。

所有任务的英文 prompt 继承：`Use the pinned checkout as evidence. Cite the relevant source symbols. State assumptions and missing information. Keep the existing public behavior unless the task explicitly requests a change.` 问答、诊断、方案额外继承 `Do not edit repository files.`；中文 goal 只用于页面。冻结给模型的业务材料也使用英文，源码、错误字面量保持原文。不得在模型材料中放参考补丁或冻结断言实现。

冻结验收必须在控制端持有，实际从候选源码导入 schedule 并校验 `schedule.__file__` 位于该候选包路径；patch 的对象也必须是该候选模块。不使用环境内另一个已安装 schedule 来“验收”。候选可改自己的测试，但接受结论依赖控制端断言和适用的冻结上游回归。

首版 `requires` 仅支持同场景任务依赖。五个场景分别使用独立工作区，从同一固定原版建立各自基线，不能跨场景隐式继承文件或 checkpoint。场景四的SC-M01仅依赖同场景SC-D04答案；场景五的SC-M02仅依赖同场景SC-U02回答，独立从场景五原版基线修复repr。两项修改各自在自己的工作区运行完整冻结上游81项集合。

业务假时钟仅替换隔离验收子进程中的 `schedule.datetime.datetime.now()`；sleep spy 仅替换 `schedule.time.sleep` 来记录间隔。不得替换平台计时器、driver timeout、累计预算、数据库状态或会话时间。时区测试使用独立子进程、明确 TZ、结束恢复；不能对宿主全局时区或其他并行验收进程生效。

非修改任务的 native 断言验证事实材料和候选无文件变动，不能独自证明自由文本回答正确；还须私有语义评审对照证据，模拟阶段只验证协议/分支和评分流，不能宣称真实模型质量已验证。方案题以原有 API 的冻结可执行见证验证可行性，不能按“包含某字符串”判通过。

资源建议均为待验证配置：单项正常 native 断言进程软上限 5 秒、硬上限 10 秒；完整原生回归软上限 15 秒、硬上限 30 秒；256 MiB、无网络、临时目录且进程回收。与平台任务累计1800秒等运行预算分别配置，不能用假时钟缩减或重置平台计费/尝试口径。

## 场景一：把日常对账接入进程内调度（3 项）

### SC-U01 — understand

- **中文 goal／业务问题**：理解从注册到真正运行的路径，确认服务为什么刚启动并不会立刻执行对账，以及多个 Scheduler 是否共享任务。
- **源码锚点**：`Scheduler.__init__` L86、`Scheduler.every` L162、`Job.do` L644、`Scheduler.run_pending` L89、`Job.should_run` L667、`Job.run` L674。
- **英文 prompt 简稿**：`Trace how a reconciliation callback is registered and executed. Explain whether registration runs it immediately and whether two Scheduler instances share jobs. Show the relevant state transitions and source symbols.`
- **冻结材料／披露**：`registration.py` 使用两个独立 Scheduler，在12:00给A注册每分钟写入合成 JSON 的回调，B空；提供文件目标与参数。材料齐备，无披露轮。
- **独立 native 断言**：12:00注册及轮询不写文件；12:01轮询实际文件为约定JSON；A有1项、B始终0项；last_run/next_run准确；再次同刻轮询不重复写。记录文件字节，不仅看自报计数。
- **允许路径／依赖／资源**：无文件编辑；无任务前置依赖；标准库；5/10秒共用预算。
- **待验证**：控制端假时钟适配与候选导入路径；回答必须区分创建Job、绑定入队和真正执行。

### SC-C01 — consult

- **中文 goal／业务问题**：判断单机轻量对账与跨机器、持久化、亚秒精度三种新增需求是否适合继续用此库，允许结论为无须修改现库或应选其他架构。
- **源码锚点**：`docs/index.rst` 的“When not to use Schedule”；`Scheduler.jobs`、`run_pending`、`Job.run`。官方固定文档 [index.rst](https://github.com/dbader/schedule/blob/82a43db1b938d8fdf60103bd41f329e06c8d3651/docs/index.rst)。
- **英文 prompt 简稿**：`Assess this pinned library for three requirements: a single-process daily report, durable scheduling across restarts, and synchronized sub-second work across machines. Recommend where it fits and where the application needs a different design. No library change is required.`
- **冻结材料／披露**：`requirements.md` 明确单进程可重建任务，另两项是对比选项而非必须全部实现；不用业务凭据或联网服务。
- **独立 native 断言**：独立进程注册任务，退出后新进程调度器为空；两个实例只各自持有列表；固定只读源码摘要无变更。语义评审核文档边界，不以短实验假装证明全部分布式性质。
- **允许路径／依赖／资源**：无编辑；可在SC-U01之后呈现但不硬依赖；标准库；两个短进程合计10秒。
- **待验证**：评分接受合理“不适合/无须改库”结论；不得把当前无持久化标成BUG或要求新增数据库。

### SC-P01 — plan

- **中文 goal／业务问题**：规划启动首跑、正常轮询、tag查询/停用和空调度器待机的最小集成流程。
- **源码锚点**：`Scheduler.get_jobs` L122、`clear` L135、`get_next_run` L177、`idle_seconds` L198、`Job.run` L674、`Job.tag` L457。
- **英文 prompt 简稿**：`Propose a minimal integration plan for one immediate startup reconciliation, recurring execution, tag-based inspection and shutdown, and an idle loop that does not busy-spin when there are no jobs. Use existing public APIs and identify the assumptions about callback failures.`
- **冻结材料／披露**：`service-requirements.md` 规定单进程、启动失败先终止启动、周期每分钟、退出停用tag=reconcile；空队列用有界默认等待。没有多线程或持久化要求。
- **独立 native 断言**：冻结见证依次调用注册后的job.run、advance一分钟后run_pending、get_jobs(tag)、clear(tag)；startup和periodic各一次、清除后next_run/idle_seconds均None；独立sleep spy证明空队列只使用默认等待。不给模型见证代码。
- **允许路径／依赖／资源**：无编辑，输出方案；无硬依赖；标准库；5/10秒。
- **待验证**：方案不伪造立即首跑参数，不对None执行数值max，不把首次手工run的取消行为误写成自动注销。

## 场景二：报告为什么晚了或少了（3 项）

### SC-D01 — diagnose

- **中文 goal／业务问题**：进程暂停30分钟后报告只执行一次，判断是否丢任务BUG，给出与补跑需求相符的建议。
- **源码锚点**：`Scheduler.run_pending` L89文档与到期筛选、`Job.run` L674、`_schedule_next_run` L700。
- **英文 prompt 简稿**：`A one-minute report was registered at 12:00. The process did not poll until 12:30 and then polled twice without advancing time. Only one report was written. Diagnose whether this matches the documented behavior and explain what a catch-up requirement would change.`
- **冻结材料／披露**：完整时线、轮询片段、单输出文件；不遗漏进程暂停事实。
- **独立 native 断言**：12:30连续两轮只调用一次，next_run12:31；12:31再一轮累计两次。与“应执行30次”相反对照，冻结文件无编辑。
- **允许路径／依赖／资源**：无编辑；无硬依赖；标准库；5/10秒。
- **待验证**：将“不补跑是设计行为，无须改代码”作为通过答案；不能凭计数就猜测模型漏调用。

### SC-D02 — diagnose

- **中文 goal／业务问题**：两分钟周期越来越偏移，区分回调执行耗时与调度算法故障。
- **源码锚点**：`Job.run` L674 在回调后设置last_run并重新排期、`_schedule_next_run` L700；`docs/index.rst` 执行耗时说明。
- **英文 prompt 简稿**：`A two-minute job starts at 12:02 and finishes at 12:02:30. Its next run is 12:04:30. Explain this result using the pinned implementation and recommend an application-level approach if business requirements instead demand a stable cadence.`
- **冻结材料／披露**：受控开始/完成时刻、真实job状态；不得使用真实30秒睡眠。
- **独立 native 断言**：执行中推进业务Clock后last_run12:02:30、next_run12:04:30；零耗时反例next_run12:04:00。语义评审接受默认契约，不要求私造fixed_rate入口。
- **允许路径／依赖／资源**：无编辑；与SC-D01是不同原因，互无前置；标准库；5/10秒。
- **待验证**：不要把callback duration从时钟中偷偷抹掉；方案应说明异步卸载需应用自己管理，不能宣称库保证实时。

### SC-C02 — consult

- **中文 goal／业务问题**：每天10点和16点各出一份报告，选择使用现有API还是为库增加多个at时点能力。
- **源码锚点**：`Job.at` L471保存单个at_time、`Job.do` L644、`Job.tag` L457、`Scheduler.get_jobs` L122。
- **英文 prompt 简稿**：`We need the same daily report at 10:00 and 16:00. A chained at('10:00').at('16:00') only retains one time. Recommend the smallest solution with the current API and discuss the maintenance tradeoff of adding a new multi-time API.`
- **冻结材料／披露**：需求限定相同回调、两个时点、同tag统一管理，允许创建两个Job；不额外要求单个Job身份。
- **独立 native 断言**：原链at_time16:00；冻结见证用两个Job、同tag，10:00与16:00分别实际写一次，get_jobs(tag)为2、clear(tag)为0；空日期间轮询不多写。
- **允许路径／依赖／资源**：无编辑；标准库，无pytz必需；5/10秒。
- **待验证**：允许“现有API足够，无须改库”；不把at的覆盖行为描述成未承诺的BUG。

## 场景三：失败后的队列行为与取消方式（3 项）

### SC-D03 — diagnose，含材料不足与披露

- **中文 goal／业务问题**：用户只说“今天报表没出来”，先判断信息不足并索取最小材料；获得完整回调和异常后再定位。
- **源码锚点**：`Scheduler.run_all` L103、`_run_job` L172、`Job.run` L674；官方固定 [exception-handling.rst](https://github.com/dbader/schedule/blob/82a43db1b938d8fdf60103bd41f329e06c8d3651/docs/exception-handling.rst)。
- **英文 prompt 简稿**：`The scheduled report did not appear today. Determine what evidence is missing before assigning a root cause. Request the smallest useful materials, then diagnose the supplied reproduction and explain whether changing the library is necessary.`
- **冻结材料／披露**：初始只有英文症状及版本，不给异常。模型提出缺少“callback code and full traceback/polling invocation”后披露 `callback.py`、`driver.py`、`traceback.txt`：首任务验证合成行失败抛ValueError，第二报表任务尚未执行；材料是正常业务校验失败。不得在初始隐藏地将原因评分成必答，不合并真实凭据日志。
- **独立 native 断言**：披露前native只能确认无输出，结论必须uncertain；披露后执行回调见证得到ValueError、事件仅failed_job、健康任务未执行；健康首任务反例两者均执行。材料交付全文/版本摘要要与实际消费输入一致。
- **允许路径／依赖／资源**：无编辑；标准库；披露是同一业务任务内新一轮，不新增任务；每轮native5/10秒，业务尝试/预算仍按平台既有规则。
- **待验证**：请求材料→真实交付→基于新证据回答完整路径；模拟review只证明分支连通，不证明真实模型正确诊断。

### SC-C03 — consult

- **中文 goal／业务问题**：完成一次导出后如何取消任务，区分CancelJob、显式cancel_job、clear(tag)和手工job.run。
- **源码锚点**：`CancelJob` L71、`Scheduler.cancel_job` L150、`_run_job` L172、`clear` L135、`Job.run` L674。
- **英文 prompt 简稿**：`Recommend how a one-off export callback should remove itself after success, and how an operator should cancel one job or a tagged group. Explain the difference between calling Job.run directly and running it through Scheduler.`
- **冻结材料／披露**：`export.py` 使用临时JSON输出，同组两任务，另组一任务；只在成功后返回CancelJob，无外部数据。
- **独立 native 断言**：手工job.run返回CancelJob但任务仍在；scheduler轮询后移除；cancel_job重复调用不误删其他项；clear(tag)只去掉同组；回调实际写入1份合成JSON。
- **允许路径／依赖／资源**：无编辑；标准库；5/10秒。
- **待验证**：取消方式不能混为同义词；不得要求核心新增once_atAPI才可交付。

### SC-P02 — plan

- **中文 goal／业务问题**：坏数据任务不要挡住健康任务，制定只处理指定业务异常、有限失败后取消的应用包装方案。
- **源码锚点**：`Job.run` L674、`Scheduler._run_job` L172、`CancelJob` L71、固定异常说明；不要求修改默认异常策略。
- **英文 prompt 简稿**：`Plan an application wrapper that handles only ReportDataError, records consecutive failures per job, cancels that job after three failures, resets the counter after success, and lets healthy jobs continue. Unexpected exceptions must still propagate. Keep Schedule's default behavior unchanged.`
- **冻结材料／披露**：`policy.md` 明确三次连续而非累计失败；两个Job独立计数；ReportDataError是冻结合成应用异常，非schedule既有类。首次成功和中间恢复轨迹都提供。
- **独立 native 断言**：控制端冻结应用见证依次输入失败、成功、失败、失败、失败，第五次取消；健康任务各轮仍产生事件；两任务计数不串；TypeError反例继续传播。见证验证可行性，不把其成功冒充模型生成实现。
- **允许路径／依赖／资源**：无编辑，输出方案；可引用SC-D03已披露材料但初始上下文独立完整；标准库；5/10秒。
- **待验证**：不得使用裸except吞掉所有错误，不声称默认库已经有on_error政策字段；响应方案按私有语义评审核对。

## 场景四：批量手工执行后的多余等待（2 项）

### SC-D04 — diagnose

- **中文 goal／业务问题**：三个短任务执行run_all(delay_seconds=2)后额外等六秒，定位任务间延迟与尾延迟的差别。
- **源码锚点**：`Scheduler.run_all` L103，循环对每项运行后无条件sleep，文档称between each job。
- **英文 prompt 简稿**：`Three short jobs are executed using run_all(delay_seconds=2). The observed sleep total is six seconds rather than four. Locate the extra delay, distinguish it from callback runtime, and describe a minimal compatible correction.`
- **冻结材料／披露**：`run_all_trace.json` 提供job0/sleep2/job1/sleep2/job2/sleep2事件，空任务与单任务对照；不真实睡六秒。
- **独立 native 断言**：原版0/1/3任务sleep调用数0/1/3、总等待0/2/6；真实回调顺序0/1/2。诊断不改文件，最后一次sleep应被指出。
- **允许路径／依赖／资源**：无编辑；标准库；5/10秒。
- **待验证**：这是真实缺陷，不能因前几题允许无需修改就一律回答设计行为。

### SC-M01 — modify

- **中文 goal／业务问题**：修复run_all只在当前批次的任务之间延迟，同时保留任务快照、执行顺序和取消处理。
- **源码锚点**：`Scheduler.run_all` L103、`_run_job` L172；上游`test_schedule.py` L1273起run_all和装饰器组。
- **英文 prompt 简稿**：`Fix Scheduler.run_all so delay_seconds is applied only between jobs in the current snapshot, with no trailing delay. Preserve execution order, existing snapshot semantics, callback arguments, cancellation handling and exception propagation. Add focused tests without changing unrelated scheduling behavior.`
- **冻结材料／披露**：SC-D04完整复现以独立附件重复提供，避免单靠前任务会话记忆；给需求与允许路径，不给参考patch。
- **独立 native 正反断言**：0/1/3项sleep次数0/0/2，正delay的事件必须job0/sleep2/job1/sleep2/job2；记录回调真实输出。取消自身不跳后项；回调中新增Job不进入当前快照；参数/装饰器保持；首回调抛错后无后续回调或额外sleep。零delay允许省略无意义sleep，不强迫某一实现。完整冻结81项原生回归必须继续通过。
- **允许路径／依赖／资源**：产品仅`schedule/__init__.py`，候选可增改`test_schedule.py`作说明；不允许改pyproject/锁/私有验收。仅依赖同场景SC-D04的诊断答案；使用场景四独立工作区及固定原版基线。标准库+冻结pytest/pytz；native5/10秒，全套15/30秒。
- **待验证**：修改前必失败的目标断言、修改后参考补丁通过、无关破坏与伪实现反例；控制端冻结上游测试不得被候选覆盖。

## 场景五：交互调试未完成配置的任务（2 项）

### SC-U02 — understand

- **中文 goal／业务问题**：解释为什么REPL查看every()会报错，而str(every())和every(2)又可以显示，定位未配置状态的真实字段。
- **源码锚点**：`Scheduler.every` L162、`Job.__init__` L227、`Job.__str__` L264、`Job.__repr__` L278，尤其`unit[:-1] if interval == 1 else unit`。
- **英文 prompt 简稿**：`Explain the difference between repr(Scheduler().every()), str(Scheduler().every()), and repr(Scheduler().every(2)) in the pinned version. Identify which unconfigured fields and formatting branch cause the exception, without assigning a default time unit.`
- **冻结材料／披露**：`interactive.txt` 含三条真实表达式及完整TypeError；不只提供截图；默认unit=None，未绑定回调、未注册。
- **独立 native 断言**：interval1的repr抛TypeError；str不抛；interval2的repr不抛且含None；三者原对象unit/job_func/next_run均None、调度器jobs为空。核对精确对照，不能按旧概要误称“全部未配置Job都会崩”。
- **允许路径／依赖／资源**：无编辑；标准库；5/10秒。
- **待验证**：这是解释/理解任务，须在场景五独立原版基线上核对上述对照；不继承场景四的修改，不要求此步提前修复。

### SC-M02 — modify

- **中文 goal／业务问题**：让未完成配置的Job安全展示，不隐式补单位、不注册或运行任务，已配置表示保持兼容。
- **源码锚点**：`Job.__repr__` L278及`Job.__str__`、`Job.__init__`；上游`test_schedule.py` repr/str/partial相关测试。
- **英文 prompt 简稿**：`Make repr safe for an unconfigured Job, including the default interval of one. Preserve the unconfigured state and the representation of configured jobs. Do not assign a default unit, register the job, or run a callback merely to format it. Add focused tests.`
- **冻结材料／披露**：SC-U02三条原版对照全文与安全展示契约；未配置具体文案不硬编码，可用清晰占位；不新增describe API。
- **独立 native 正反断言**：every()/every(2)/未绑定回调的repr和str均返回非空字符串；打印前后unit、job_func、last_run、next_run、jobs摘要一致；已配置interval1/2、随机范围、绑定位置/关键字参数、functools.partial的既有输出按冻结对照保持；格式化不得触发回调。在场景五独立工作区运行完整冻结上游81项，不要求通过场景四新增的M01目标。
- **允许路径／依赖／资源**：只允许`schedule/__init__.py`和候选`test_schedule.py`；仅依赖同场景SC-U02回答，从场景五独立原版基线实施repr修复；冻结pytest/pytz；native5/10秒，全套15/30秒。
- **待验证**：参考patch与原版失败对照尚未制作；必须特别检查直接把unit改成seconds的伪修复会被状态断言拒绝。

## 后续 wave：python-dotenv 与 Tenacity

这里只列真实能力与适配难点，不为未选项目虚构首批冻结任务数。

- python-dotenv 可形成“理解加载/插值与环境优先级→询问是否必须改库→不完整配置材料的诊断→文件编辑保真→两项修复”的10–14项后续包。优先修复`Variable.resolve` L64的`${B:-d}`空值默认语义，以及`main.py:set_key` L224/rewrite L162的非目标CRLF保留；正常反例分别为缺失/非空值、纯LF与BOM/合法转义。前者有兼容变化，不能直接沿旧行为宣称修复无风险。`DotEnv.set_as_environment_variables` L101、`resolve_variables` L333的os.environ优先级必须核对；合成env只放隔离子进程，不读取宿主真实.env。全套CLI需要实际可执行入口和Click，IPython为回归依赖，不能因只做核心任务漏掉适用回归。无需围绕认证、口令或攻击设计任务。
- Tenacity 可形成“理解retry/stop/wait→用已有策略规划文件就绪重试→材料不足索取完整异常与策略→零倍率等待诊断/修复→统计解释”的10–14项后续包。已读`wait_exponential.__call__` L227、`wait_exponential_jitter.__call__` L320、`BaseRetrying.wraps` L381以及`RetryCallState` L590。零倍率attempt1025返max与sum1000策略递归为历史已复现；本轮未重复。两修复候选可选零倍率和组合递归，但后者须保持浮点分组/用户子类/动态策略语义，不能为了任务数采用粗暴flatten。运行用wait_none或注入sleep并记录调用，业务time.monotonic仅在验收子进程内控制，外层平台timeout保持真实。同步强制超时、任意generator自动恢复不做首批能力承诺；异步/重入统计单列后续复杂任务。

## 实施前明确未完成的事项

1. 本文13项是候选规格，不是已接入正式任务；场景与任务ID须在子任务中映射真实catalog schema，不猜字段名。
2. 首次制作冻结materials及独立native验收，记录每个文件SHA；为两修改制作原版失败、参考成功及反例拒绝证据。当前只有原版最小复现已重核。
3. 按实际平台内容模型表达同场景依赖SC-D04→SC-M01、SC-U02→SC-M02；各场景独立工作区、独立固定原版基线，不通过跨场景requires或隐式checkpoint累计继承。M01与M02分别通过自身目标和完整冻结上游81项，其余问答任务不因排序而伪造业务依赖。
4. 现有研究文档提及“ProjectVerifier仅app.py”的表述是当时接入状态，平台已后续支持其他原生工程；本轮不据旧句推断当前产品缺陷。实际适配点由平台代码研究负责核对。
5. 当前正式Python小版本/ABI、离线依赖profile、解压临时空间修复、candidate路径、只读信任边界、当前镜像资源需在子任务验证；不能将旧镜像81项通过冒充本轮通过。
6. 不开始真实模型运行、OAuth、线上账号修改、发布或部署。模拟验证只证明素材、调度、披露、私有评审协议和native断言路径可运行；真实回答质量与成本另行校准。
