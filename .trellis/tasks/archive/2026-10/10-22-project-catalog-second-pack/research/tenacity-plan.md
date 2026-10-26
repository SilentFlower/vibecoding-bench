# Research: Tenacity 第二批内容规划

- Query: 在冻结重试工程上设计五类真实任务，核实零倍率、组合等待、同步／异步边界及主测试／子测试的可信回归对账。
- Scope: mixed；只读源码、上游测试、旧基线及当前runner，纯计算短复现；仅写本研究文件，不制作参考修复或修改共享执行器。
- Date: 2026-10-22

## Findings

### 结论与数量

建议 **5 场景、13 个唯一任务**：understand 2、consult 3、diagnose 4、plan 2、modify 2；11项非修改。两项修改是“零倍率指数贡献避免无意义溢出”和“内置组合树无递归求值且保留原语义”。重入统计异常只做诊断，不在本批顺带修改复杂调用生命周期。披露、unavailable、测试矩阵及多次试跑均不加任务数。

### 来源、文件与接口

- 官方 [jd/tenacity](https://github.com/jd/tenacity/tree/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6)，固定提交 `32ac68f0941319c0d2f4fb927f96e4ee29bb46c6`。2026-10-22官方commits API返回完整SHA一致；GitHub网页抓取受限后用官方API核实，没有采用第三方镜像。
- 本地冻结工程 `.deploy/github-100-research/core-utils/tenacity/source/`；Apache-2.0，`LICENSE`及源码版权头应保留。历史97个跟踪文件；pyproject要求Python≥3.10，hatch-vcs动态版本。浅检出产生的 `0.1.dev1+g32ac68f09` 是构建元数据，不能当正式发行号或额外修改 `_version.py`。
- `tenacity/__init__.py:258` 的 `BaseRetrying` 接受sleep/stop/wait/retry/before/after/before_sleep/reraise/retry_error_callback/name/enabled；`:381` 的wraps为每调用copy但复用wrapper.statistics；`:416` begin清统计；`:434` iter按action流调度；`:461` after只进入决定重试的分支；`:473` stop决定耗尽／下一次sleep；`:537` Retrying循环执行真实用户函数；`:590` RetryCallState保存attempt_number/outcome/upcoming_sleep/idle_for等。
- `tenacity/wait.py:37` 的wait_base相加创建二叉wait_combine；`:44` 的反向加法只认sum起始整数0，并支持普通callable；`:95` 的wait_combine保存原wait_funcs tuple，`:102`按顺序 `float(sum(x(retry_state) for x in wait_funcs))`。源码已经支持位置参数callable，不重复提出该修复。
- `tenacity/wait.py:227` wait_exponential先对正倍率做数学封顶判断，然后幂计算／乘法，OverflowError返回max；`:274` random_exponential使用父类结果作为uniform上限；`:320` exponential_jitter先取jitter，之后算指数贡献，加法后按min/max约束。
- `tenacity/stop.py:89` stop_after_attempt按已完成编号判断；`:100` stop_after_delay比较已完成outcome的seconds_since_start，可能跨最后一段等待；`:120` stop_before_delay把upcoming_sleep也计入。两者都不能强制中断已经运行的同步业务函数。
- `tenacity/asyncio/__init__.py:75` AsyncRetrying明确await用户async函数和sleep；`:144` 起将同步／异步回调适配为awaitable；`:188` 提供异步迭代；`:211` wraps保留协程函数属性。默认异常谓词在 `tenacity/retry.py:120` 为Exception，业务显式retry_if_exception_type(FileNotFoundError)不会吞CancelledError。

### 本轮最小实证与真实问题边界

本轮以宿主Python3.12.3、`python3 -B`只读导入冻结源码，使用 `SimpleNamespace(attempt_number=...)` 仅作为等待策略接收的编号载体；控制器业务验证仍须用真实RetryCallState。没有真实sleep、配置读写、完整pytest或模型请求。

| 纯计算输入 | 原版结果 | 结论 |
| --- | --- | --- |
| attempt1025、multiplier整数0、exp_base整数2 | fixed=0，min3→3，jitter0.25→0.25 | 正常反例，不能称“所有0都会错误” |
| attempt1025、multiplier浮点0.0、exp_base整数2、max60 | exponential=60；min3仍60；random上限60；jitter结果60 | 大整数转浮点时OverflowError，零贡献误封顶 |
| attempt1025、multiplier整数0、exp_base浮点2.0、max60 | 同样误封顶 | 先算浮点幂溢出；不是只修float乘法即可 |
| attempt1、上述零组合 | fixed0、min3→3、jitter0.25→0.25 | 小编号正常 |
| `sum(wait_fixed(1) for _ in range(1000))` | 求值RecursionError | 深左关联组合真实失败 |
| 同1000项直接 `wait_combine(*items)` | 1000.0 | 原有平组合正常 |
| `(wait_fixed(1e16)+wait_fixed(1))+wait_fixed(-1e16)` | 0.0 |
| 三叶直接flat combine | 1.0 | Python3.12 sum补偿与原树分组可观察不同，不能flatten重排 |
| wait_combine子类的__call__额外加7，包外再+4；子类原叶为1与2 | 14.0 | 展平子类会误成7，必须尊重自定义求值 |

前两种溢出都须进入目标冻结断言；整数0＋整数底数是必须继续正常的对照。random.uniform替身用端点四分之一计算，记录实际参数，而非无视上下界返回固定数。对于当前业务明确支持的正且有限底数、attempt≥1、合法min/max，不在本任务新增任意NaN参数政策。正倍率、早封顶、jitter采样顺序及边界都保留既有上游语义。

### 材料、评分与依赖共用契约

- 页面title/goal中文；下列英文User question用于模型首问，冻结附件指令、branch.when与rubric也英文。原源码、报错、合成中文业务值原样保留。
- 所有非修改 `allowed_paths=[]`、不产生代码接受检查点。除 TN-D01 外初始材料齐备、无隐藏披露／无unavailable分支。TN-D01初始不能把隐藏异常类或最终策略提前写成必答事实。
- 五个场景各自独立原版；所有任务 `requires=[]`。两项修改自带完整复现和契约，不需要消费先前诊断回答；默认D→M仅为顺序，不虚构answer依赖，可从给足相同材料的直接修改入口进入。**没有code依赖，也没有从M01跨场景继承M02**；各修改独立通过目标与完整适用原生回归。
- 所有sleep spy、random替换、业务time.monotonic替换只在独立验收子进程内，不改平台timeout、累计预算或全局运行时钟。替身会记录参数与顺序，实际业务仍调用候选库、执行回调并观察临时文件／事件。
- native对只读题验证事实和现有API方案见证，文本结论由私有语义评审核；模拟只能证明协议、材料消费和分支流，不证明真实模型回答质量。

### 场景与任务表

#### TN-S01：等配置文件就绪再继续启动（3 项）

**TN-U01 / understand / goal：理解 retry、wait、stop 和回调的调用顺序。**

- User question: `Trace the supplied local file loader through Retrying: two FileNotFoundError outcomes followed by success on the third attempt. Explain when retry, wait, stop, before_sleep and sleep are evaluated, and why success does not trigger another wait. Do not edit files.`
- 公开：完整有限策略（retry FileNotFoundError、stop_after_attempt(3)、wait_fixed(0.2)）、第3次before发布合成JSON、已记录事件。无隐藏／无unavailable。
- 合法结果：`explained`，区分attempt编号、sleep次数、stop总尝试而非额外重试；成功不走after／wait分支。
- 独立正常／反例：真实临时文件前两次不存在，第3次原生before发布文件后真实读JSON；函数3次、sleep2次且各0.2、返回内容精确；首尝试已有文件对照1次、0sleep。不依据候选自报统计断言业务次数。
- allowed_paths `[]`；requires `[]`。

**TN-C01 / consult / goal：只重试暂态缺文件，保留配置解析错误。**

- User question: `A configuration file may appear a little later, but malformed JSON must fail immediately. Recommend existing retry and stop policies for at most three total attempts. Do we need to modify Tenacity? Explain the difference from retrying every Exception.`
- 公开：缺文件是唯一暂态错误，坏JSON为最终错误；无网络／服务。无隐藏／无unavailable。
- 合法结果：`advice_no_code_change`；现有retry_if_exception_type(FileNotFoundError)、stop_after_attempt足够；不要扩大到JSONDecodeError／所有OSError。
- 独立正常／反例：真实文件第三次发布可成功；坏JSON第一次直接传播JSONDecodeError、sleep0；永久缺失恰3次、sleep2后按reraise政策结束。成功读回原JSON不只返回硬编码成功。
- allowed_paths `[]`；requires `[]`。

**TN-P01 / plan / goal：规划有界文件就绪重试与正常启动失败处理。**

- User question: `Plan a local startup loader that retries only a missing file, reads valid JSON once available, reports final failure clearly and does not repeat any already completed startup side effect. Use existing public APIs, a bounded attempt policy and application-level validation.`
- 公开：读文件与validate成功前不得创建“启动完成”标志；初始化副作用不可自动重放；最多3次、有界等待，字段验证失败立即停止。无隐藏／无unavailable。
- 合法结果：`viable_plan_no_library_change`；将可重试读取边界包小，后续业务动作在成功结果之后，明确RetryError/reraise选择，不虚构事务回滚。
- 独立正常／反例：控制端现有API见证第三次读成功后才写一次启动标志；永久缺失／无效JSON／字段校验失败均无标志，最后两类不被无差别重试。见证不是候选新代码的验收替代。
- allowed_paths `[]`；requires `[]`。

#### TN-S02：重试排查与运行观测（4 项）

**TN-D01 / diagnose / goal：先索取完整异常和重试策略，再判断为何没有重试。**

- User question: `The loader failed once instead of retrying. Determine which minimal evidence is missing before assigning a cause. Request the complete exception type and retry configuration, then diagnose the supplied reproduction. Do not edit files.`
- 初始公开：版本与“只执行了一次”症状；不预给异常类型／策略。请求后正常披露 loader.py使用retry_if_exception_type(FileNotFoundError)、坏JSON文件及JSONDecodeError traceback、实际事件一次；不含真实业务配置。
- unavailable：若无法提供异常和调用配置，交付英文说明，允许 `insufficient_information`，列出可检验假设与最小材料；不选定“库吞重试”。正常披露为 `diagnosed_no_code_change`，谓词不匹配是正确行为。
- 独立正常／反例：消费后实际JSONDecodeError1次、sleep0；缺文件反例走3次及2sleep；披露前只要求请求信息，不按隐藏异常强制具体结论。披露属于同一任务，不新加业务尝试。
- allowed_paths `[]`；requires `[]`。

**TN-C02 / consult / goal：选择最终异常、RetryError 与显式 fallback。**

- User question: `After three missing-file attempts, should our caller receive RetryError, the original FileNotFoundError or a fallback object? Compare reraise and retry_error_callback in this version and choose an explicit application policy without modifying the library.`
- 公开：调用方三类接口需求对照、最后异常、fallback值为合成只读对象；无隐藏／无unavailable。
- 合法结果：`advice_no_code_change`；解释默认包装、reraise=True最终原异常、callback返回值替代耗尽分支，不能说callback返回后会再reraise，也不能把不可重试异常视为耗尽callback路径。
- 独立正常／反例：真实三次缺失在三种政策分别观测RetryError及其last_attempt／FileNotFoundError／fallback；不可重试JSONDecodeError直接传播且callback计数0；首成功不触发fallback。
- allowed_paths `[]`；requires `[]`。

**TN-U02 / understand / goal：区分 after 与调用最终完成事件。**

- User question: `The after hook is absent on first-attempt success and on the final successful attempt after earlier failures. Explain whether this matches the pinned lifecycle, contrast before and before_sleep, and suggest where an application should observe final completion without claiming a new hook.`
- 公开：三个完整事件轨迹：首成功、两失败后成功、三失败耗尽；同一策略；无隐藏／无unavailable。
- 合法结果：`explained_no_code_change`；after在决定重试的结果后执行，包括最终耗尽失败；不是finally／success hook。应用在外层正常返回／except/finally处理最终完成。
- 独立正常／反例：实际before次数分别1/3/3、after0/2/3、before_sleep0/2/2、sleep0/2/2；显式不可重试失败after0。按实际调用顺序记录，不能仅看字典计数。
- allowed_paths `[]`；requires `[]`。

**TN-D02 / diagnose / goal：区分重入包装器统计与当前调用真实尝试。**

- User question: `The attached recursive use of one retry-decorated function reports wrapper statistics that do not match the outer call's attempt number. Diagnose which state is shared, distinguish observations from RetryCallState, and propose a bounded application workaround without modifying Tenacity.`
- 公开：旧observe.py对应的有限重入函数、逐层事件及外层真实编号；没有并发线程，不要求修复杂统计发布契约。无隐藏／无unavailable。
- 合法结果：`diagnosed_with_workaround`；wraps虽copy controller却复用statistics字典，重入相互clear／更新，不能推断外层真的执行4次；可按真实RetryCallState回调记录调用身份或各调用独立控制器，不承诺wrapper.statistics跨重入隔离。
- 独立正常／反例：当前镜像重做旧原版“外层第2次时共享stats为4”的有限复现，并独立事件计数、RetryCallState编号和嵌套深度；非重入两次失败／成功统计正常作对照。若当前固定源码行为复现不符，先更正材料，不硬编码旧数字。
- allowed_paths `[]`；requires `[]`。

#### TN-S03：等待预算与异步取消（2 项）

**TN-C03 / consult / goal：解释 stop_before_delay 的边界及同步超时能力。**

- User question: `We have a five-second retry window and a next wait of four seconds after two seconds have elapsed. Compare stop_after_delay and stop_before_delay. Can either stop a synchronous function that is already blocked? Recommend the appropriate boundary without modifying Tenacity.`
- 公开：业务时间线、单次函数耗时与sleep分开、严格要求不再开始越界下一次尝试；无隐藏／无unavailable。
- 合法结果：`advice_with_limits`；stop_before_delay会在2+4≥5时停止而after_delay在已耗2时不停止；不可声称硬中断同步函数或自动取消所有外部资源。
- 独立正常／反例：真实RetryCallState的outcome_timestamp与upcoming_sleep由业务子进程控制，边界2+3=5也停止、2+2<5不停止；长运行函数完成后才有outcome，未抛失败的首成功不会被stop策略倒追取消。外层真实deadline不patch。
- allowed_paths `[]`；requires `[]`。

**TN-P02 / plan / goal：用已有异步控制器规划可取消的文件就绪流程。**

- User question: `Plan an async local loader with bounded missing-file retries and an outer asyncio timeout. Cancellation must propagate immediately rather than become another retry. Use AsyncRetrying or the existing async decorator, explain the role of an awaitable sleep, and avoid promising interruption of arbitrary synchronous work.`
- 公开：async调用方、只重试FileNotFoundError、最多3次、调用方持有总timeout、每次本地读取有界；无隐藏／无unavailable。
- 合法结果：`viable_async_plan`；outer asyncio.wait_for／等价受支持上下文管理等待异步任务，取消不被catch-all吞；不添加per_attempt_timeout参数，不混用同步sleep阻塞event loop。
- 独立正常／反例：真实async函数前两次缺失、第3次读到实际合成文件；async sleep spy记录且await后让出事件循环；取消等待中任务，CancelledError传播且不开始第N+1次；永久缺失有限耗尽。只在业务子进程做有界真实取消，平台超时保持真实。
- allowed_paths `[]`；requires `[]`。

#### TN-S04：零倍率为什么跳到等待上限（2 项）

**TN-D03 / diagnose / goal：定位浮点零倍率的大编号溢出。**

- User question: `At attempt 1025, wait_exponential(multiplier=0.0, max=60) returns 60 instead of zero. Compare integer and float multipliers and bases, then explain the corresponding random-exponential and additive-jitter behavior without actually sleeping. Do not edit files.`
- 公开：参数与本轮原版表、未发生真实等待、min3与deterministic RNG对照；无隐藏／无unavailable。
- 合法结果：`diagnosed`；指出先算幂／大整数转float再乘，OverflowError路径返回max；整数0＋整数2本身正常，jitter型仍应保留随机贡献而非全归零。
- 独立正常／反例：用真实RetryCallState设attempt1025／更大编号实际调策略，0.0＋int2与int0＋float2均误max；小编号、int0＋int2、正倍率封顶对照；记录random.uniform参数及采样次数。
- allowed_paths `[]`；requires `[]`。

**TN-M01 / modify / goal：零指数贡献保持下界和抖动，不误跳上限。**

- User question: `Avoid computing an irrelevant exponential contribution when the multiplier is zero in wait_exponential and wait_exponential_jitter. Preserve min/max ordering, random-exponential bounds, one jitter draw and all non-zero behavior. Cover integer and float zero/base cases without changing public signatures or sleeping.`
- 公开：重复TN-D03完整参数、合法正有限base、attempt≥1、既有上游测试保护；无隐藏／无unavailable。
- 合法结果：`implemented`；fixed结果为原clamp规则下零贡献，random_exponential使用正确区间，jitter仍先采样再加零贡献并clamp。不能粗暴 `if multiplier==0: return 0` 抹掉min/jitter。
- 独立正常／反例：0.0/int0、int2/float2、attempt1/1024/1025/2049，非零min、jitter0／确定性正采样、max小于jitter、正倍率正常增长及现有提前封顶ExplodingPower对照；与原版小编号输出相同，真正溢出失败两路恢复；实际控制器使用修复策略两次失败后成功，sleep spy收到预期，不产生真实长等待。
- allowed_paths `['library/tenacity/wait.py','library/tests/test_tenacity.py']`；requires `[]`。场景独立原版，自足材料支持直接修改，不依赖先前诊断answer或组合修复。

#### TN-S05：大型组合等待策略（2 项）

**TN-D04 / diagnose / goal：解释深组合栈溢出及不能直接展平的原因。**

- User question: `A sum of 1000 wait_fixed strategies raises RecursionError, while one flat wait_combine works. Explain the shape created by + and why flattening every nested strategy could change floating-point grouping or custom strategy calls. Do not edit files.`
- 公开：1000项左关联构建、平组合、浮点分组和自定义子类四个完整受控例子；无隐藏／无unavailable。
- 合法结果：`diagnosed`；结构递归深度与正常列表长度不同；不能推荐增大sys.setrecursionlimit为库修复，不能忽略自定义__call__。
- 独立正常／反例：原版深树RecursionError、平1000正常1000.0；浮点分组0.0而flat1.0、自定义子类外加4结果14.0；加入实际叶调用事件证明左到右一次求值。完整调用在有界子进程内，无真实等待。
- allowed_paths `[]`；requires `[]`。

**TN-M02 / modify / goal：迭代求值内置组合树，同时保留分组与自定义策略。**

- User question: `Evaluate deeply nested built-in wait_combine trees without relying on Python recursion. Preserve each node's original float(sum(...)) grouping, left-to-right leaf calls, callable argument convention, custom subclasses and changes visible when a node is entered. Do not flatten opaque strategies or raise the global recursion limit. Reject cyclic built-in combination graphs with a clear ValueError while allowing shared acyclic subtrees. Add focused tests.`
- 公开：TN-D04所有复现与新增精确契约；明确自定义策略为不透明callable，其自身内部递归不在库承诺内；循环原本栈溢出，改为ValueError是本任务明示授权的更窄有界错误。无隐藏／无unavailable。
- 合法结果：`implemented`；可用显式帧栈保存每节点子结果并在该节点使用同一builtin sum／float，不展开自定义子类；不能用手写 `total += leaf`代替Python3.12 sum算法。实现选择不限，但可观察顺序必须一致。
- 独立正常／反例：1000/2000级左关联、右关联与混合，空节点0.0、shared DAG重复出现时按每出现次求值；普通lambda仅接位置参数、falsy callable照常执行；子类__call__额外值保留；上述float分组及非有限值原行为／异常按原版浅树作动态oracle；叶异常后不调用后续叶；前叶修改尚未进入的子节点wait_funcs要可见，进入节点时取得的既有tuple迭代语义不追随父属性重绑；自环／两节点环快速ValueError而不是hang，不能把合法shared DAG当环。候选通过目标后还须完整适用回归。
- allowed_paths `['library/tenacity/wait.py','library/tests/test_tenacity.py']`；requires `[]`。本场景从原版开始，自足材料支持直接修改，不依赖先前诊断answer，也不要求TN-M01新增目标同场景累积。

### 主测试、子测试与当前runner的实际核对

旧证据 `baseline-tests.log` 最后一行是 **185 passed, 15 subtests passed**；`baseline-result.json` 记录junit_passed=200。本轮重新用ElementTree解析原XML发现：

| 口径 | 实际旧证据 |
| --- | --- |
| `testsuite@tests` 汇总属性 | 200 |
| 实际 `<testcase>` 元素数 | **185** |
| 日志主测试 | 185 |
| 日志子测试 | 15 |

因此旧文档“JUnit200”应理解为suite汇总计量，**不是200个collection节点或200个testcase元素**。不能把185与200重复相加，更不能由200推断现有runner严格主节点比较必失败。

当前 `orchestrator/project_native_regression.py:294` 收集item.nodeid；`:308` 的logreport保存id/when/outcome但未保存report具体类型／context；`:325` 按同id归并结果；`:437` 读取实际testcase元素，`:446` 强制 `collection唯一数 == xml_cases`，**该条件与旧185元素证据相容，应保留**。当前未有Tenacity SUITES，首次实现先增加实际suite并在目标镜像完整校准，再依据结果确认是否存在必须的计数适配，不因为原先推测放宽成大于等于。

pytest9.1.1历史venv的真实源码与[官方9.0变更](https://docs.pytest.org/en/stable/changelog.html#pytest-9-0-0-2025-11-05)、[官方子测试说明](https://docs.pytest.org/en/stable/how-to/subtests.html)一致：pytest≥9.0内置subtests并支持unittest.TestCase.subTest；本仓用的是后者，**不需要另装pytest-subtests插件**。pytest较旧版本若采用独立插件是另一套环境，需要真实锁定／校准，不能当本批默认，也不能通过降级或禁用subtests消掉分母。

实际可用于可信补充冻结的字段已读：

- 旧venv `_pytest/subtests.py:80`：`SubtestReport`继承TestReport，仍有父nodeid／when／outcome；`.context` 为SubtestContext，含 `msg: str|None`、`kwargs: Mapping[str,Any]`。
- 同文件`:58` 的SubtestContext将kwargs值转成pytest saferepr文本；其 `_to_json()` 返回msg/kwargs；report序列化标记为 `_report_type='SubTestReport'` 和 `_subtest.context`，大小写不同于类名，不能猜字段。
- `_pytest/unittest.py:427` 的addSubTest为每个unittest子项构造SubtestReport，经同一个pytest_runtest_logreport输出；空参数subTest可能context完全相同，因此单靠context作为key会错误去重。
- `_pytest/junitxml.py:502`按nodeid／worker复用reporter，`:529`按各call报告增加统计。故同一个主项多次子call报告累加suite计数，却仍可只有一个testcase元素。

若实现阶段为Tenacity补最小可信子测试证据，建议**仅该新suite opt-in**：保存真实report类型，并为每个父node按实际出现顺序赋ordinal，冻结 `{parent_nodeid, ordinal, when, context.msg, context.kwargs, outcome}`；保持主节点及旧schema默认校验，原六仓私有脚本不原地升级。基线／候选的子项条目全量一致，子项failed/error/skip等与父项分别归档；防止同context重复子项被折叠、候选缺少子执行被主项pass覆盖。saferepr可能含对象地址，**只在实际固定测试context稳定时直接冻结**；若目标校准出现易变值，先研究窄而可审计的规范化，不能盲目freeze全部repr或按数量放行。本方案不要求为了计数改测试、删子项、加独立插件或重写既有六仓回归。

### 离线环境、同步／异步与资源

1. 本仓顶层包布局 `package=tenacity, implementation_dir=tenacity, import_root='.'` 可沿现有默认；实际import必须指向候选受控树，不能指向venv预安装库。产品无必需外部运行依赖。
2. 完整适用 `python -m pytest tests` 需要pytest、tornado及trio的真实依赖；pyproject的test extra列pytest/tornado，trio在dev组，但tests/test_asyncio.py有trio路径，不得因未装trio把它跳过后称全套通过。标准asyncio由 `asyncio.run` 包装测试，**没有发现需要pytest-asyncio的入口**；不因看到async函数猜装插件。
3. 历史清单为pytest9.1.1、tornado6.5.10、trio0.34.0、attrs26.1.0、outcome1.3.0.post0、sniffio1.3.1、sortedcontainers2.4.0等；需按实际wheel metadata和当前Python冻结传递依赖/hash，不能把其他仓的pytest版本自动当本仓最终准入。hatch-vcs是构建时需求；若直接源码import且不需要发行版本，不必在业务期联网build。
4. 旧镜像 `ci-39482854683-1` Python3.12.3、UID1000、256MiB、PID128，无网络／账号HOME，完整185主＋15子通过、0skip/error，pytest2.996秒，整体3.863秒、峰值49148KiB；这些是历史证据，不是当前目标镜像已通过。实施首步必须实际校准当前Python及非空完整节点合同，分别记录主项、子项、XML汇总及元素口径。
5. 资源建议起点业务256MiB、10秒；完整回归256～512MiB、30秒，深树目标1000/2000节点有界运行。均待当前镜像实测，预装准备预算单列；不改平台计时，不通过更高全局栈限制掩盖问题。

### 相关规范与证据

- `.trellis/spec/vibecoding-bench/backend/project-iterations.md` 的schema2、原生候选导入／完整合同、隐藏材料及真实项目准入契约。
- 本任务 `prd.md`；母任务 `research/operations-candidates.md` 的后续wave；旧 `research/github-projects/tenacity.md`、`tenacity-roadmap-20.md`、原始 `observations-result.json`、`baseline-tests.xml` 和日志。旧“只支持app.py”的历史句已过时，不据此另建平台。
- 官方固定源码：[wait.py](https://github.com/jd/tenacity/blob/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6/tenacity/wait.py)、[控制器](https://github.com/jd/tenacity/blob/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6/tenacity/__init__.py)、[异步控制器](https://github.com/jd/tenacity/blob/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6/tenacity/asyncio/__init__.py)、[原生测试](https://github.com/jd/tenacity/blob/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6/tests/test_tenacity.py)、[LICENSE](https://github.com/jd/tenacity/blob/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6/LICENSE)。官方API核对入口 `https://api.github.com/repos/jd/tenacity/commits/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6`。

## Caveats / Not Found

- 本文是逐项可实施规划，尚未生成正式manifest、英文业务材料、rubric、冻结native、wheel profile或两个私有参考实现；数量不计当前已准入。
- 零倍率失败依赖float参与的大幂溢出；整数0＋整数2正常，必须保留正常反例。不得写成所有0都错误或忽略min/jitter后“修复”。
- 深组合的正确性主要难点是原分组、子类调用、动态节点和shared DAG／cycle区别；如果无法证明这些契约，保持该项未完成，不能用flatten加大数字掩盖。
- 200为历史XML汇总，实际185个testcase；当前runner是否需要扩展须以目标镜像为证，保留现有严格比较。子测试补充合同只应新增Tenacity opt-in，不改变原六仓内容或历史合同。
- 未运行本批当前镜像完整回归／参考正例与错误候选负例，未测当前资源或真实模型语义。没有真实模型、OAuth、生产配置、产品代码修改、提交或部署。
