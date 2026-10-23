# Tenacity：二十步原生工程路线

固定 [jd/tenacity@32ac68f0941319c0d2f4fb927f96e4ee29bb46c6](https://github.com/jd/tenacity/tree/32ac68f0941319c0d2f4fb927f96e4ee29bb46c6)。原版实测三项缺陷，其余十七项为已读控制器、策略、回调与异步入口后的增强提案，不代表上游承诺。观察记录在 `.deploy/github-100-research/core-utils/tenacity/observations-result.json`。

每项包含实现、文档、正反验收和累计原生 `python -m pytest tests`，不拆测试或重试计数。模块相对 tenacity/，原生测试位于 tests/。除明确组合关系外各项独立；新增入口名只是提案。已有 enabled、name、retry_with/copy、wait_exception、stop_before_delay、异步回调、可 pickle 控制器和异常原因环保护不重计。现有自定义 stop/wait/retry、sleep 与回调可以手工组合多数增强；提案新增的是明确的原生状态、生命周期或策略契约，默认行为保留。

## 01．零倍率指数等待不跳到上限（修复）

- 来源：[官方 #710](https://github.com/jd/tenacity/issues/710)，wait.py 的指数／随机指数／指数抖动路径。原版 attempt=1025、multiplier=0.0 返回 60，预期零贡献。
- 交付：先处理零贡献，避免无意义大幂转换；保留 min、jitter、max 的顺序与边界。
- 验收：浮点／整数底数、零倍率、非零 min、确定性 jitter、正常大倍率封顶；test_tenacity.py。仅计算等待，不实际睡 60 秒；同根三路径合一步。

## 02．大型等待组合不依赖 Python 栈深（修复）

- 来源：[官方 #748](https://github.com/jd/tenacity/issues/748)，wait_base.__add__/wait_combine。原版 sum(1000个wait_fixed) 抛 RecursionError，flat wait_combine 对照为 1000。
- 交付：迭代评估内置组合链；保留浮点括号分组、求值顺序、用户子类覆盖和动态修改语义，不粗暴展开再重新求和。
- 验收：大左关联／右关联／混合链、空组合、回调异常、非有限值、子类 __call__；test_tenacity.py。环形策略明确拒绝，不能另造无限循环。

## 03．重入与并发调用的统计隔离（修复）

- 来源：[官方 #701](https://github.com/jd/tenacity/issues/701)，BaseRetrying.wraps。报告原本为静态线索，本轮已实际复现：外层第2次尝试的 statistics.attempt_number 为4。
- 交付：运行中每次调用独立统计，完成后按明确政策发布包装器视图；仍满足 functools.wraps 外层装饰器读取统计的原有需求。
- 验收：单线程递归、两线程事件同步、并发异步任务、异常结束、包装器套包装器；test_tenacity.py／test_asyncio.py。不能只替换共享 dict 导致外层引用永久失效。

## 04．按调用上下文临时覆盖重试政策（增强）

- 来源：[官方 #506](https://github.com/jd/tenacity/issues/506)。retry_with 返回新包装器，enabled 是已有配置，但不能沿调用栈只覆盖当前请求而不修改全局对象。
- 交付：retry_context 使用 ContextVar 明确覆盖可选 stop/wait/retry/enabled；嵌套退出恢复，禁止修改共享默认策略实例。
- 验收：嵌套、异常退出、两个 asyncio 任务、跨线程显式传播政策、未进入时原行为；__init__.py／asyncio/__init__.py，test_tenacity.py／test_asyncio.py。

## 05．完整调用的成功与结束回调（增强）

- 来源：[官方 #531](https://github.com/jd/tenacity/issues/531)。当前 after 仅在决定重试后执行，不等同于首次成功／重试成功后的调用结束事件。
- 交付：统一生命周期完成回调，标记首次成功、重试后成功、耗尽与不可重试失败；同步／异步皆恰好一次，不改变现有 after 含义。
- 验收：所有结束分支、reraise、retry_error_callback、自定义钩子抛错与异常链；__init__.py／asyncio，test_after.py／test_asyncio.py。多个结束原因属于一步。

## 06．可组合的重试谓词取反（增强）

- 来源：[官方 #625](https://github.com/jd/tenacity/issues/625)。现有原因类型检查没有通用 retry_not／~ 组合，用户可自写 lambda。
- 交付：对已有谓词与 callable 取反，明确成功结果、异常结果和无 outcome 时的规则；异步谓词先 await 再取反。
- 验收：原因链匹配／不匹配／环、and/or 组合短路、异步返回 False、谓词自身异常；retry.py／asyncio/retry.py，test_tenacity.py／test_asyncio.py。禁止直接对 coroutine 对象求 bool。

## 07．随机等待使用显式随机源（增强）

- 来源：可复现实验和多请求隔离。wait_random／wait_random_exponential／wait_exponential_jitter 使用模块 random，公开签名无 rng；当前只能 monkeypatch 全局。
- 交付：opt-in RNG 注入，各策略遵循同一调用约定，默认仍用现有随机源；不假装提供密码学随机性。
- 验收：种子重现、stub 边界、最小／最大、不同实例互不影响、copy 与序列化边界；wait.py，test_tenacity.py。不同随机策略不拆成三步。

## 08．保存上次等待的去相关抖动（增强）

- 来源：争用负载需要 decorrelated jitter；当前 full jitter 和加性指数抖动已存在，未提供每次调用有状态的该策略。
- 交付：wait_decorrelated_jitter 的 previous-delay 状态属于 RetryCallState，而非共享策略实例；明确基础值、封顶和重置。
- 验收：确定性随机轨迹、上限、两次调用重置、并发复用策略不串扰、非法范围；wait.py／RetryCallState，test_tenacity.py。可用独立 RNG，不硬依赖第07步。

## 09．按累计等待预算停止（增强）

- 来源：任务允许计算很久，但重试休眠总量不能超过预算。stop_after_delay 包含计算耗时；目前可用自定义 stop 检查 idle_for，没有原生明确口径策略。
- 交付：stop_after_sleep 区分已计划等待和即将等待，并在超预算前停止；说明提前唤醒时名义与实际休眠的差异。
- 验收：刚好到界、零等待、长计算但短休眠、动态等待、event 提前唤醒；stop.py／__init__.py，test_tenacity.py。不把它称作真实墙钟 deadline。

## 10．嵌套重试共享绝对截止时间（增强）

- 来源：调用树中每层相对重试预算相加会超过请求期限。stop_before_delay 只针对单次控制器起点，当前没有共享 deadline 上下文。
- 交付：同一 monotonic 截止时间沿 ContextVar 传播，首次调用／后续尝试／睡眠前检查，等待裁到剩余额度。
- 验收：嵌套控制器、已过期不开始新尝试、临界睡眠、异步取消、无 deadline 原行为；__init__.py／asyncio／stop.py，test_tenacity.py／test_asyncio.py。不承诺强制中断已运行的同步函数。

## 11．跨调用共享重试配额（增强）

- 来源：多个请求各允许三次会整体放大故障流量。现有 stop 是逐 RetryCallState，无共享令牌预算。
- 交付：可注入 RetryBudget，首次调用与重试分开计量，原子取得配额；定义补充、耗尽和成功返还政策。首版仅进程内，不新增服务。
- 验收：多线程竞争不超发、耗尽不睡／不发新请求、失败回调、不同业务预算隔离；stop.py／控制器调度，test_tenacity.py。可自定义 stop 替代，但新预算本身须有独立可验的状态模型。

## 12．多个控制器共享尝试并发上限（增强）

- 来源：限制同时执行的重试尝试，与第11步总次数配额不同。现有 before/after 可手写信号量，但 after 不是所有结果的 finally。
- 交付：尝试级 ConcurrencyLimiter，计算结束立即归还许可，休眠不持有；同步与 asyncio 许可明确分型，等待可截止／取消。
- 验收：首成功／异常／停止／取消均归还、同限额多函数、递归避免死锁的政策、休眠时其他任务可进入；__init__.py／asyncio，test_tenacity.py／test_asyncio.py。禁止隐式进程全局限流器。

## 13．开始尝试前检查外部取消（增强）

- 来源：stop_when_event_set 与 sleep_using_event 已存在，但 stop 通常在失败后检查，预置取消仍可能开始新尝试。
- 交付：可选 CancellationGuard 在初次及下一次调用前检查；与可唤醒 sleep 配合，明确专用取消异常和异步取消传播。
- 验收：初始已取消、休眠中取消、不同键／任务不互相取消、自定义 retry_if_not_exception_type 不吞 guard；nap.py／控制器，test_tenacity.py／test_asyncio.py。不强杀正在运行的同步用户代码。

## 14．异步单次尝试超时（增强）

- 来源：总重试 stop 不能限制某次 await 永不完成；当前需用户额外包 timeout。
- 交付：AsyncRetrying 的 opt-in per-attempt timeout，把超时作为选定可重试失败；外层任务取消立即传播，不转换成内部超时重试。
- 验收：及时返回、超时后重试、超时耗尽、任务取消、deadline 剩余不足、清理子任务；asyncio/__init__.py，test_asyncio.py。兼容最低 Python 的实现选择要实测，不添加假装可中断线程的同步对等参数。

## 15．带检查点的分页读取重试（增强）

- 来源：装饰 generator 函数只重试“创建 generator”，不管理后续迭代失败；普通已抛错 generator 也不能自然继续。
- 交付：独立 retry_pages(fetch_page,initial_token)，每页取得成功后才发布下一 token；仅重试当前整页，不重放已交付页，调用者保管 checkpoint。
- 验收：第2页失败再成功、永久失败、空尾页、重复 token／环、取消、恢复指定 token；控制器与新增分页适配测试。不是通用“恢复任意 generator”，不自动推断有副作用代码的幂等性。

## 16．异常组的叶子重试政策（增强）

- 来源：并发任务的 ExceptionGroup 不等价于单层异常类型；现有 retry_if_exception_type 只看外层，可自定义谓词遍历替代。
- 交付：递归 any/all 叶子政策，默认保守要求全部可重试，明确定义 BaseExceptionGroup 中断叶子的处理；保持原异常组结构用于最终报告。
- 验收：嵌套组、混合可重试／不可重试、取消叶子、原因链、Python3.10 不可用时明确能力边界；retry.py／asyncio，test_tenacity.py／test_asyncio.py。不自动重跑其中一个已成功的业务子任务。

## 17．有界的尝试历史（增强）

- 来源：RetryError 仅持 last_attempt，statistics 是摘要；用户可 after 手工记录，但成功分支与保留上限需自行处理。
- 交付：AttemptHistory 保存不可变的编号／耗时／结局摘要，限制条数与内容大小，可替换值脱敏器；不默认保留 traceback／实参对象引用。
- 验收：首成功、重试成功、耗尽、超过记录上限、异常对象回收、并发隔离；RetryCallState／RetryError，test_tenacity.py。不依赖第05步的公开回调，可直接由调度路径记录。

## 18．可脱敏的结构化重试日志（增强）

- 来源：before_sleep_log 目前把异常或返回值直接插入文本；签名只有 logger/log_level/exc_info/sec_format，现有自定义 callback 可替代。
- 交付：独立结构化记录工厂，显式字段、值大小界限、异常／结果 sanitizer，支持选择是否含业务值；原有文本 helper 保留。
- 验收：合成口令异常不会原样泄漏、非字符串结果、超长值、formatter 出错、重试名与次数准确；before_sleep.py／before.py／after.py，test_tenacity.py／test_after.py。不声称只删除实参就能保证异常字符串安全。

## 19．每次尝试的资源上下文（增强）

- 来源：每次失败后须先释放文件／回滚事务再休眠。现有 AttemptManager 收集 outcome，不提供可注入的每尝试资源生命周期；before/after 也不是完整 finally。
- 交付：注入 sync/async context manager 工厂，每尝试各创建一次，进入失败和退出异常的主异常政策明确；资源退出后才计算下一次尝试。
- 验收：成功关闭、用户异常清理、enter/exit 抛错、取消、休眠前资源已释放；AttemptManager／控制器／asyncio，test_tenacity.py／test_asyncio.py。应用自己定义事务行为，不自动修改任何数据库。

## 20．白名单声明式策略配置（增强）

- 来源：服务通过配置选择 stop/wait/retry，当前只有 Python 对象构造，没有 policy_from_dict；可由应用自行写配置工厂替代。
- 交付：版本化纯映射配置，内置策略白名单与应用显式注册项；校验参数／组合／引用并导出可审查描述，不 eval、任意 import 或载入 callable 路径。
- 验收：往返相同策略、未知名字／参数、循环引用、预算非法、同步策略误配异步、配置不执行合成恶意字符串；新增配置模块及测试，同时回归全部原生集合。首版只支持已存在内置策略，不依赖前十九步都实现。

## 验收边界

以上增强未实施，原版缺口观察不是改进后验收。冻结测试须实际加载候选 Tenacity，使用受控 sleep/timer/RNG、事件同步及真实文件结果累计回归；不以候选自报 statistics 为唯一证据。完整原生集合与单步验收的预算要分别确认，再接入平台原生工程适配。
