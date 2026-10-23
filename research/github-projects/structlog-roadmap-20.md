# Structlog：二十步真实工程迭代路线

固定 [hynek/structlog@19c4f21059e853114efa7a93b6e675d93bf7934e](https://github.com/hynek/structlog/tree/19c4f21059e853114efa7a93b6e675d93bf7934e)，原生证据见[单仓审查](./structlog.md)。以下 1 项修复与 19 项增强是本地研究路线，尚未实施；增强不代表上游承诺。每项包含实现、测试和说明，不把测试或重试拆步。

## 01．有序渲染区分缺字段与显式空值

- **来源／原版**：KeyValueRenderer、LogfmtRenderer 的 drop_missing 文档只说丢失缺字段，_items_sorter 实际把存在的 None 也丢掉；原版已实证。
- **交付与模块**：用独立缺失哨兵修正两个渲染器共享的排序路径；`src/structlog/processors.py:_items_sorter`。
- **兼容**：保持字段顺序、默认行为和原字典消费策略；显式 None 按各渲染器原空值语法输出。
- **正常／边界验收**：存在 None 输出 `value=None`／`value=`，不存在时省略；覆盖 False、0、空串、排序开关和重复 key_order。
- **原生回归／依赖**：`tests/processors/test_renderers.py`；无步骤依赖，沿用冻结测试环境。

## 02．递归解码结构化事件中的字节值

- **来源／原版**：导入任务将嵌套结果写日志；UnicodeDecoder 目前只解码顶层，实际嵌套 bytes 仍保留。
- **交付与模块**：增加明确可选的递归处理模式，支持映射值和常见序列，保留容器类型及字段路径诊断；`src/structlog/processors.py:UnicodeDecoder`。
- **兼容**：默认仍只处理顶层；不擅自改字典键、不解码任意对象、不修改调用者共享容器。
- **正常／边界验收**：嵌套中文 bytes 按指定编码转换；坏字节遵循 errors，循环结构、深度预算、tuple 与空容器有明确行为。
- **原生回归／依赖**：`tests/processors/test_processors.py`；标准库，无步骤依赖。

## 03．批量字段改名与冲突策略

- **来源／原版**：对齐不同报表字段名；EventRenamer 仅处理 event，通用映射需自写处理器。
- **交付与模块**：新增映射改名处理器，提供冲突报错／保留／覆盖及原子应用；`src/structlog/processors.py:EventRenamer`、`src/structlog/typing.py`。
- **兼容**：现有 EventRenamer 不变；新处理器不把 a→b、b→c 误作连续覆盖，默认冲突拒绝。
- **正常／边界验收**：同时重命名多个字段且无关字段保留；缺字段、互换、重复目标及 event 冲突不丢数据。
- **原生回归／依赖**：`tests/processors/test_processors.py`；标准库，无步骤依赖。

## 04．可组合的常见业务类型 JSON 编码

- **来源／原版**：金额和日期报表；JSONRenderer 已支持自定义 serializer 和 __structlog__，Decimal 默认为 repr 字符串，尚无类型适配注册表。
- **交付与模块**：新增独立可组合适配器，显式登记 Decimal、日期、UUID、dataclass 等类型的编码策略；`src/structlog/processors.py:JSONRenderer`。
- **兼容**：不替换默认 fallback；金额字符串或数字必须由调用者选定；已有 __structlog__ 优先级明确且可配置。
- **正常／边界验收**：登记 Decimal 字符串编码后保持精度，datetime 输出明确时区；未知类型、递归 dataclass、适配器抛错及自定义 default 不被吞掉。
- **原生回归／依赖**：`tests/processors/test_renderers.py`；标准库，无步骤依赖。

## 05．按嵌套路径投影事件字段

- **来源／原版**：从订单 payload 中选客户名和总价生成摘要；目前只能自写处理器，未有路径投影入口。
- **交付与模块**：新增明确路径段序列的投影处理器，指定输出别名和缺失策略；`src/structlog/processors.py`、`src/structlog/typing.py`。
- **兼容**：不把点号字段名自动解释为路径；仅输出声明投影与明确保留字段，不隐式展开整棵对象树。
- **正常／边界验收**：两条嵌套路径产生准确扁平摘要；字面点号、列表下标、缺失与显式 None 区分，目标冲突提前拒绝。
- **原生回归／依赖**：`tests/processors/test_processors.py`；标准库，无步骤依赖。

## 06．完整嵌套事件的可逆扁平化

- **来源／原版**：向列式本地报表写完整事件，不能预先列举全部路径；当前无通用扁平化处理器，与第05步有限投影不同。
- **交付与模块**：增加带路径编码、碰撞检测和最大深度的整棵映射扁平化，附反向恢复约定；`src/structlog/processors.py`。
- **兼容**：新处理器 opt-in；列表默认保留，不把数字键猜为数组；冲突默认报错，不覆盖原值。
- **正常／边界验收**：普通嵌套 dict 扁平化后按路径还原等价结构；空 dict、含分隔符键、共享子对象和循环引用有边界断言。
- **原生回归／依赖**：`tests/processors/test_processors.py`；标准库，无步骤依赖，不强制依赖第05步。

## 07．结构化事件模式校验报告

- **来源／原版**：本地数据管道要求 event、quantity 有稳定类型；现有 callable 链可手写校验，没有内置规则和结构化报告。
- **交付与模块**：新增小型事件校验处理器，声明必需字段、类型／谓词、额外字段策略及失败报告；`src/structlog/processors.py`、`src/structlog/exceptions.py`。
- **兼容**：默认处理链不加校验；不把日志库变成自动类型转换框架，失败策略必须显式选择。
- **正常／边界验收**：有效订单事件原样通过，多个坏字段一次报告准确路径；bool 与 int、None、用户谓词异常和未知规则有明确定义。
- **原生回归／依赖**：`tests/processors/test_processors.py`、`tests/test_base.py`；标准库，无步骤依赖。

## 08．可选花括号事件模板处理器

- **来源／原版**：同一日志模板需复用命名字段；PositionalArgumentsFormatter 目前按百分号语法消费 positional_args，不能把已有功能当作新增花括号模式。
- **交付与模块**：新增独立格式处理器，显式花括号 style、字段来源及格式后字段保留策略；`src/structlog/stdlib.py:PositionalArgumentsFormatter`、`src/structlog/processors.py`。
- **兼容**：既有百分号处理器不变；模板仅使用声明字段，禁止隐式属性遍历与自动执行任意表达式。
- **正常／边界验收**：命名数量与金额按模板格式化且结构字段仍可选保留；转义花括号、缺字段、坏格式和非字符串 event 行为稳定。
- **原生回归／依赖**：`tests/test_stdlib.py`、`tests/processors/test_processors.py`；标准库，无步骤依赖。

## 09．命名时区与固定精度时间戳

- **来源／原版**：跨地区日报需要固定业务时区；TimeStamper 仅 fmt、utc、key，实际签名没有命名时区或精度参数。
- **交付与模块**：新增显式 tzinfo／ZoneInfo 与 ISO 精度选项，UTC/local 旧参数兼容校验；`src/structlog/processors.py:TimeStamper`。
- **兼容**：默认 UTC 输出完全不变；不能同时指定互斥策略；依赖系统 IANA 数据时明示部署要求。
- **正常／边界验收**：同一瞬间在 UTC 与指定地区偏移正确，毫秒精度固定；DST 折叠、未知时区、pickle 往返与 UNIX timestamp 保持正确。
- **原生回归／依赖**：`tests/processors/test_processors.py`；标准库 zoneinfo，必要时固定 tzdata，无步骤依赖。

## 10．Logfmt 结构值的 JSON 编码模式

- **来源／原版**：把嵌套计数结果交给支持 logfmt 的本地工具；当前容器值通过 str 输出 Python 字面量，原版已观察。
- **交付与模块**：为 dict/list 值增加显式 JSON 适配模式，正确完成 logfmt 引号及反斜杠编码；`src/structlog/processors.py:LogfmtRenderer`。
- **兼容**：默认 str 模式保持；标量 bool/None 语法不变；不暗示 logfmt 自身定义嵌套类型。
- **正常／边界验收**：读取 logfmt 后对结构值做 JSON 解码得到原 dict/list；嵌套引号、Unicode、换行、非 JSON 类型和循环明确失败或显式适配。
- **原生回归／依赖**：`tests/processors/test_renderers.py`；标准库，不强制依赖第04步。

## 11．业务操作配对事件与单调时钟耗时

- **来源／原版**：导入阶段需要 begin/end/error 与耗时；时间戳已有，但没有业务计时上下文。
- **交付与模块**：新增显式上下文帮助器，用单调时钟生成配对事件、操作标识、结束状态和 elapsed；`src/structlog/_generic.py`、`src/structlog/contextvars.py`。
- **兼容**：不覆盖应用异常，不宣称事务回滚；默认不自动生成开始事件，调用者明确选取事件策略。
- **正常／边界验收**：正常结束产生一对同标识事件及非负耗时；异常、取消、嵌套操作和同步／异步上下文各恢复原绑定。
- **原生回归／依赖**：`tests/test_generic.py`、`tests/test_contextvars.py`；标准库，无步骤依赖。

## 12．任务局部的事件顺序号

- **来源／原版**：同一离线处理任务的多条日志需稳定排序，时间戳会相同；没有内置 EventSequence。
- **交付与模块**：新增 ContextVar 作用域序号处理器和显式 reset，说明并行子任务的继承／分支策略；`src/structlog/processors.py`、`src/structlog/contextvars.py`。
- **兼容**：序号只在声明作用域中保证递增，不声称多进程全局顺序；默认不新增日志字段。
- **正常／边界验收**：同一作用域连续事件得到1、2、3，另一个独立作用域从1开始；嵌套、copy_context、线程与取消不串计数。
- **原生回归／依赖**：`tests/test_contextvars.py`、`tests/processors/test_processors.py`；标准库，无步骤依赖。

## 13．任务隔离的日志捕获上下文

- **来源／原版**：并发测试独立捕获各自日志；capture_logs 明确非线程安全，当前直接改全局 processor 列表。
- **交付与模块**：新增任务局部捕获入口及作用域分流处理器，不改其他任务的配置；`src/structlog/testing.py:capture_logs`、`src/structlog/contextvars.py`。
- **兼容**：保留旧 capture_logs 行为及零配置使用；新入口明确要求安装分流处理器，不能假称拦截任何第三方 logger。
- **正常／边界验收**：两个交错 asyncio 任务只捕获本任务事件；嵌套捕获、异常退出、缓存 logger 和非参与任务仍按约定运行。
- **原生回归／依赖**：`tests/test_testing.py`、`tests/test_contextvars.py`；标准库，无步骤依赖。

## 14．明确支持异步处理器的日志链

- **来源／原版**：应用已有异步字段计算函数；原生 ainfo 等是把同步处理链移至执行器，_process_event 不逐个 await 处理器。
- **交付与模块**：新增独立异步 wrapper/协议，按序支持同步与 awaitable 处理器，并保留调用方上下文；`src/structlog/_native.py`、`src/structlog/_base.py`、`src/structlog/typing.py`。
- **兼容**：现有同步和异步快捷方法保持；同步入口不自动启动事件循环；明确并发与取消语义。
- **正常／边界验收**：同步→异步→渲染器按序交付事件；异步 DropEvent、取消、错误、跨循环使用和返回类型错误均有独立验收。
- **原生回归／依赖**：`tests/test_native.py`、`tests/test_base.py`；标准库 asyncio，无步骤依赖。

## 15．条件分支子处理链

- **来源／原版**：摘要事件和明细事件采用不同字段处理但共用输出；当前可自写 callable，缺少内置分支组合器。
- **交付与模块**：新增条件子链，声明条件、处理器序列和是否继续外层链，禁止中途错误终止类型混淆；`src/structlog/processors.py`、`src/structlog/_base.py`。
- **兼容**：处理器协议和外层顺序不变；渲染器只允许处于明确终止分支；分支不隐式复制到多个输出端。
- **正常／边界验收**：两类事件走各自声明分支且共享最终输出；条件抛错、DropEvent、无匹配、嵌套和错误返回类型可定位。
- **原生回归／依赖**：`tests/processors/test_processors.py`、`tests/test_base.py`；标准库，无步骤依赖。

## 16．重复事件合并与显式刷新摘要

- **来源／原版**：长时导入反复报告同一进度类别；现有链没有带计数摘要的合并器，应用需自行维护状态。
- **交付与模块**：新增有界事件聚合器，按声明键合并、单调窗口和容量触发摘要，并提供显式 flush；`src/structlog/processors.py`、`src/structlog/_output.py`。
- **兼容**：默认不合并；不能默默丢掉最终计数；调用者决定是否保留首条、窗口和 shutdown 刷新。
- **正常／边界验收**：相同键的五条事件输出首条与数量正确摘要，不同键独立；时钟倒退、容量满、异常退出、并发与空刷新均明确。
- **原生回归／依赖**：`tests/processors/test_processors.py`、`tests/test_output.py`；标准库，无步骤依赖。

## 17．处理器耗时与调用量诊断

- **来源／原版**：调优 JSON 日志成本需区分字段处理和渲染开销；没有逐处理器 profile 入口，只能手写包装。
- **交付与模块**：新增可关闭的链包装器，输出阶段调用量、累计耗时与失败／丢弃计数，诊断走独立回调；`src/structlog/_base.py`、`src/structlog/testing.py`。
- **兼容**：关闭时无新增事件字段；诊断不递归调用被测链，不把业务时间与处理器耗时混算。
- **正常／边界验收**：可控时钟下各阶段计数与耗时准确，结果事件保持相同；DropEvent、异常、嵌套链和回调错误各有规则。
- **原生回归／依赖**：`tests/test_base.py`、`tests/test_testing.py`；标准库，无步骤依赖。

## 18．容量受限的原生捕获器

- **来源／原版**：长时间集成测试需限制日志留存；CapturingLogger 目前无参数且无限追加 calls。
- **交付与模块**：增加显式容量与覆盖最旧／拒绝新增策略，公开 total/dropped 计数及快照读取；`src/structlog/testing.py:CapturingLogger`、`CapturingLoggerFactory`。
- **兼容**：默认无容量限制且 calls 仍遵守原类型；新模式清楚说明快照与动态列表差别，不在后台悄悄改历史对象。
- **正常／边界验收**：容量3记录5条时留下声明的3条并报告2条未保留；容量0、负值、并发、clear 和多工厂隔离覆盖。
- **原生回归／依赖**：`tests/test_testing.py`；标准库，无步骤依赖，与第13步隔离范围独立。

## 19．处理链异常的阶段诊断

- **来源／原版**：某自定义处理器抛错时应用难确定阶段；_proxy_to_logger 仅特别处理 DropEvent，其他异常不附阶段信息。
- **交付与模块**：增加显式诊断包装器，为错误提供处理器索引／名称、方法和原始 cause，支持独立失败回调；`src/structlog/_base.py`、`src/structlog/exceptions.py`。
- **兼容**：默认直接传播行为保持；不吞 BaseException，不默认输出整个事件内容；回调失败不能覆盖最初异常。
- **正常／边界验收**：第三阶段失败可准确定位且保留原 cause；匿名 callable、递归回调、DropEvent、异步取消和渲染返回错类型分别验证。
- **原生回归／依赖**：`tests/test_base.py`、`tests/test_native.py`；标准库，不强制依赖第17步。

## 20．显式上下文字段合并策略

- **来源／原版**：任务公共属性与单条事件发生同名时需可审查规则；merge_contextvars 当前固定 setdefault，事件值优先，不能选择深层合并或记录冲突。
- **交付与模块**：新增独立配置式上下文合并器，支持明确浅层优先级、可选嵌套映射合并及冲突回调；`src/structlog/contextvars.py:merge_contextvars`。
- **兼容**：原函数完全保持；新模式不修改上下文保存值，不对任意对象递归合并，不自动清理上下文。
- **正常／边界验收**：相同输入按不同声明策略得到确定值和冲突明细；None、异构类型、共享嵌套映射、任务切换与缺失字段不混淆。
- **原生回归／依赖**：`tests/test_contextvars.py`；标准库，无步骤依赖。
