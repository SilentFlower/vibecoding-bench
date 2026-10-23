# Backoff：二十步原生工程路线

固定 [litl/backoff@d82b23c42d7a7e2402903e71e7a7f03014a00076](https://github.com/litl/backoff/tree/d82b23c42d7a7e2402903e71e7a7f03014a00076)，版本2.2.1。上游已经归档，本路线是维护试点研究，不代表上游会接受改动。前七项有固定原版复现，其余十三项是增强；观察在 `.deploy/github-100-research/core-utils/backoff/observations-result.json`。

每步交付实现、文档和正反验收，运行原生 `python -m pytest tests` 累计回归。模块均指 backoff/ 下的真实文件；同步、异步、参数矩阵、文档和失败重试不另拆步。已有 runtime、动态max参数、异步handlers、raise_on_giveup、日志级别和wait_gen_kwargs保留；新接口名为提案。现有自定义等待生成器、handlers、giveup与外部包装是增强的替代方式，不声称现有系统毫无可用方案。

## 01．总时间预算包含本次尝试耗时且不受墙钟回拨影响（修复）

- 来源：[官方 #186](https://github.com/litl/backoff/issues/186)、[#149](https://github.com/litl/backoff/issues/149)。_sync/_async 在调用前计算 elapsed；受控时钟模拟首调60秒后失败、预算1秒，原版仍开始第2次调用。
- 交付：用单调时钟在完成尝试和开始下一尝试前检查，等待按真实剩余预算截断；首次至少尝试一次的既有政策明确保留。
- 验收：慢失败不再发第2次、时钟回拨控制、慢成功仍返回、到界、sync/async；test_backoff.py／test_backoff_async.py。不能中断正在运行的同步函数，不以真实睡60秒作测试。

## 02．等待生成器耗尽仍遵守 raise_on_giveup（修复）

- 来源：有限 constant(interval=[]) 原版 on_exception 即使 raise_on_giveup=False 仍抛ValueError，_sync/_async 的StopIteration分支绕过该参数。
- 交付：所有耗尽终止路径统一执行已配置放弃政策；保留最后原始异常、回调一次性与异常链。
- 验收：空／有限等待序列、flag真／假、正常max_tries终止、predicate模式仍返回末值；test_backoff.py／test_backoff_async.py。predicate返回0本轮是通过对照，不误报为崩溃。

## 03．复用装饰器不累积默认处理器（修复）

- 来源：[官方 #179](https://github.com/litl/backoff/issues/179)。同一decorate包装三次，单次放弃日志实际为1／2／3条，_decorator中nonlocal列表被重复配置。
- 交付：按每次decorate创建独立handler集合，不改变输入iterable或之前包装器；默认日志与用户回调各调用一次。
- 验收：三次复用、多个目标、同步／异步混用、handler生成器的明确一次性政策；test_backoff.py／test_backoff_async.py。不能通过全局删日志handler隐藏重复。

## 04．partial与可调用对象不会被日志名称访问遮蔽原错误（修复）

- 来源：[官方 #210](https://github.com/litl/backoff/issues/210)。原版functools.partial在默认日志路径抛AttributeError，掩盖本应传播的ValueError。
- 交付：安全获取显示名称，partial可回溯底层callable；没有__name__时使用稳定类型名，避免repr泄漏绑定实参。
- 验收：partial、callable实例、方法、lambda、无名对象；test_backoff.py／test_integration.py。真实返回／异常与logger=None对照一致，不新增业务调用。

## 05．异步giveup和事件可调用对象正确await（修复）

- 来源：_async._ensure_coroutine只识别协程函数。实际async __call__返回False的giveup被当truthy协程对象，原版第一次失败就放弃，且产生未await告警。
- 交付：对异步callable和返回Awaitable的包装函数取实际完成值；普通同步回调仍直接执行，异常按原链传播。
- 验收：异步实例／partial／包装函数、返回True／False、同步回调、回调内部异常、未await告警为零；test_backoff_async.py。本项不偷偷将predicate也改成异步，后者是第12步独立能力。

## 06．动态配置与jitter内部TypeError不被当作签名不匹配（修复）

- 来源：_common._maybe_call／_next_wait以捕获TypeError猜签名；原版max_tries函数自己抛TypeError后被吞，目标反而成功执行。
- 交付：根据调用契约区分需要求值的无参配置和传给runtime的值函数；只在确认旧零参jitter签名时走兼容，函数内部TypeError原样传播。
- 验收：配置内部错误不执行目标、必需参数错误、合法动态值、runtime value函数、旧jitter及内部异常；test_backoff.py／test_backoff_async.py／test_jitter.py。保留仍支持的弃用警告。

## 07．有上限的指数生成器避免中间幂溢出（修复）

- 来源：_wait_gen.expo。base=1e308、factor=1e-308、max_value=5，原版前两项正常，第三次在比较上限前抛OverflowError，数学结果应封顶5。
- 交付：对递增有限配置先做可证明的封顶判断或稳定计算；不因重新结合浮点运算随意改变正常序列。
- 验收：极大底数与极小factor、正常封顶、零factor、衰减底数、无上限的明确溢出政策；test_wait_gen.py。不同指数输入属于同一修复，不拆步。

## 08．导入库保留应用已经设定的日志级别（增强）

- 来源：[官方 #71](https://github.com/litl/backoff/issues/71)。独立进程先设ERROR=40，再import backoff后变为INFO=20；_common显式setLevel。
- 交付：约定只有未配置时应用库默认值，保留应用明确级别和handler；兼容旧默认输出的迁移说明。
- 验收：导入前设置、默认NOTSET、重复import、配置传播、NullHandler不重复；test_backoff.py／test_integration.py。按日志政策增强处理，不把所有既有默认行为称作bug。

## 09．重试与等待配置的明确校验（增强）

- 来源：max_tries仅用相等检查、等待与预算缺少统一验证，零／负／NaN等配置可能意外失去上限；当前签名未提供验证政策。
- 交付：静态值装饰时、动态值每次调用解析后校验；None保留无限含义，tries必须正整数，时间与等待的有限／非负约定明确。
- 验收：bool与int区分、0／负数／NaN／inf、动态返回错误类型、合法无上限；_decorator/_common，test_backoff.py／test_wait_gen.py。新严格模式或兼容迁移须显式选择。

## 10．事件详情包含实际政策与终止原因（增强）

- 来源：[官方 #221](https://github.com/litl/backoff/issues/221)。details当前含target/args/kwargs/tries/elapsed和部分结果，拿不到已求值max_tries/max_time或稳定giveup原因。
- 交付：统一只读事件快照，含实际政策、结果／异常和max次数／时间／主动giveup／等待耗尽原因，供日志或UI判断；保留旧键。
- 验收：动态配置只求值一次、四种终止原因、成功值None、handler不能改影响下一handler的状态；_sync/_async/_common，test_backoff.py／test_backoff_async.py。可用partial手工传静态上下文的替代不隐藏。

## 11．放弃判断获得本次调用上下文（增强）

- 来源：[官方 #46](https://github.com/litl/backoff/issues/46)。giveup只收异常，无法根据请求参数和尝试状态决定是否重试，除非外层另建闭包。
- 交付：独立giveup_context(details)契约，提供本次args/kwargs/tries及异常；与已有giveup互斥或顺序政策明确，异步可await。
- 验收：同一函数不同参数决定不同、并发不串、判断器抛错、None参数、异常类型未匹配不触发；_decorator/_sync/_async，test_backoff.py／test_backoff_async.py。不是把第10步事件回调的返回值偷偷作为决策。

## 12．异步结果谓词（增强）

- 来源：异步目标的结果需通过异步状态查询决定继续；目前_async.retry_predicate直接调用predicate，不await，giveup可异步不等于predicate也支持。
- 交付：允许返回bool或Awaitable[bool]的predicate，取得实际结果再决策；同步路径遇异步谓词明确拒绝。
- 验收：await后True／False、普通谓词、谓词异常／取消、误配同步目标、事件值正确；_async/_decorator，test_backoff_async.py。默认operator.not_保持。

## 13．显式注入sleep与时钟（增强）

- 来源：[官方 #125](https://github.com/litl/backoff/issues/125)。同步硬编码time.sleep，异步硬编码asyncio.sleep；只能monkeypatch模块做仿真或定制运行时。
- 交付：sleep/timer作为独立保留参数，不混入wait_gen_kwargs；同步与异步sleep返回类型分别校验，默认继续现有运行时。
- 验收：fake clock精确推进、等待计数、异步可取消sleep、hook异常、不改变业务参数；_decorator/_sync/_async，test_backoff.py／test_backoff_async.py。此为扩展点，不重复计算第01步默认计时修复。

## 14．显式尝试循环支持重试代码块（增强）

- 来源：[官方 #18](https://github.com/litl/backoff/issues/18)。单个context manager不能重新执行任意with块，目前仅装饰callable。
- 交付：for attempt in attempts(...): with attempt 的明确循环模型，初版异常重试；提供async for版本并复用预算／事件，不伪装成自动重跑with。
- 验收：两次失败一次成功、break、循环提前close、未处理异常、异步取消、嵌套循环独立；新增attempt模块及测试，回归全部原生测试。结果谓词支持另行定义，不暗中从with返回值推断。

## 15．放弃后计算显式备用返回值（增强）

- 来源：[官方 #181](https://github.com/litl/backoff/issues/181)。raise_on_giveup=False目前只能返回None，事件handler返回值不作为业务返回。
- 交付：fallback(details)返回备用值，可async；只在显式放弃政策下执行，记录来源，不改变默认reraise或handler语义。
- 验收：备用None／0／对象、动态异常信息、fallback自己失败、预算和生成器耗尽、成功不调用；_decorator/_sync/_async，test_backoff.py／test_backoff_async.py。第02步是修复已有flag，本项新增业务返回能力。

## 16．包装器按调用配置派生与禁用（增强）

- 来源：[官方 #199](https://github.com/litl/backoff/issues/199)、[#206](https://github.com/litl/backoff/issues/206)。动态max参数已存在，但没有公开retry_with或安全禁用入口，max_tries=0也不是禁用契约。
- 交付：从原始目标派生新包装器、显式enabled控制，禁用时执行一次且保留签名；不原地改共享handler集合。
- 验收：派生不影响原实例、禁用目标异常原样、两线程不同配置、动态值和事件政策；_decorator，test_backoff.py／test_backoff_async.py。只计一项配置生命周期交付。

## 17．合作取消整个重试循环（增强）

- 来源：[官方 #47](https://github.com/litl/backoff/issues/47)。asyncio任务取消可打断sleep，但无统一同步事件取消和尝试前检查。
- 交付：opt-in cancel_event/token在初次／下一次尝试前检查，等待可唤醒；取消是独立结束原因，不让宽泛exception参数吞掉。
- 验收：初始取消不调用、睡眠中取消、并发token隔离、async CancelledError、清理handler；_sync/_async/_decorator，test_backoff.py／test_backoff_async.py。不强制终止运行中的同步代码。

## 18．结果与异常共享一次重试预算（增强）

- 来源：[官方 #91](https://github.com/litl/backoff/issues/91)的嵌套策略需求。两个装饰器可组合，但各自独立计算次数和等待，不能表达一条共享尝试序列。
- 交付：on_result_or_exception在同一循环内判断匹配结果或异常，允许分支选等待策略但共享max_tries/max_time；不改变两个原装饰器。
- 验收：结果失败→异常→成功只消耗三次、未匹配异常直接抛、分支等待切换、事件唯一；_decorator/_sync/_async，test_backoff.py／test_backoff_async.py。旧嵌套行为是对照，不直接称为bug。

## 19．Retry-After的秒数／日期与最短等待政策（增强）

- 来源：[RFC9110§10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)。runtime已支持用户提取响应值，不能再声称异步Retry-After完全不可用；缺少可复用的HTTP-date、非法值与最短等待政策。
- 交付：无requests依赖的可选wait适配器，通过用户extractor取得头值；解析非负整数秒或HTTP日期，明确缺失／过去日期、jitter与剩余预算冲突时的放弃政策。
- 验收：秒数、未来／过去GMT日期、坏值、重复头政策、抖动不能提前到最短等待前；_wait_gen/_common，test_wait_gen.py／test_backoff_async.py。仅合成响应，实际网络无需可用。

## 20．每次调用的只读重试结果摘要（增强）

- 来源：handlers可自行采集，但包装器没有retry_info，外部无法稳定读取最近当前上下文的尝试／等待／终止摘要。
- 交付：不可变summary，含实际次数、计划等待、耗时、终止原因；运行中状态按线程／任务隔离，默认不保留参数、结果和traceback引用。
- 验收：首成功、重试成功、耗尽、异常退出、嵌套与并发、用户读取不能修改状态；_sync/_async及包装器，test_backoff.py／test_backoff_async.py。不自动生成无上限历史或承诺跨进程统计。

## 冻结验收边界

本轮只验证原版；七项缺陷观察不意味着已修复，十三项新能力未实现。后续验收应核对真实候选backoff加载路径，用受控时间／日志／协程和文件副作用累计验证。原生测试保留，独立验收、离线依赖和平台原生入口适配分别落地。
