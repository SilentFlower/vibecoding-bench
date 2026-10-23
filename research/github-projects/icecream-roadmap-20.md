# IceCream：二十步真实工程路线

固定 [gruns/icecream@05af3e95b0080162813bb017de90966bc75f3b91](https://github.com/gruns/icecream/tree/05af3e95b0080162813bb017de90966bc75f3b91)。原生基线 65 通过、0 跳过；范围和限制见 [单仓审查](./icecream.md)。类型计数：{"修复": 2, "增强": 18}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．展开参数不漏值（修复）

- 来源／实际场景：icecream.py:_formatArgs的zip；debug(*values,303)真实调用。
- 原版现状：返回101/202/303正确，但输出只含101与202，实参和AST节点并非一一对应。
- 用户交付：所有已计算实参都输出；能确定的来源保留，无法确定的展开用序号/组标识。
- 影响模块：icecream.py:_formatArgs/_constructArgumentOutput。
- 兼容边界：不得重新求值源表达式或二次遍历已消费生成器；返回对象身份保持。
- 正常验收：单一*list加尾参全部显示且尾参对应303。
- 边界／错误验收：多个*展开、空展开、generator、字面值和源码不可用都不漏值/错误标注。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．可选可视字符串模式（增强）

- 来源／实际场景：[上游#220](https://github.com/gruns/icecream/issues/220)与argumentToString实测。
- 原版现状：单引号未完整引用，tab/backspace/NUL/零宽字符直接进入输出；多行被原样展开。
- 用户交付：增加显式visible模式，对控制/不可见字符和引号进行可辨认转义。
- 影响模块：icecream.py:argumentToString与字符串注册器；配置。
- 兼容边界：默认可读多行行为可保留；bytes/str不能互相混同，不把内容执行为转义。
- 正常验收：含引号/tab/NUL/零宽字符能从输出判断真实字符。
- 边界／错误验收：双引号、反斜杠、Unicode双向控制、空串、多行和字面\n区别明确。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．Windows 颜色上下文异常也恢复（修复）

- 来源／实际场景：supportTerminalColorsInWindows实际模拟win32/异常。
- 原版现状：init被调用一次，异常后deinit为0。
- 用户交付：使用finally确保颜色包装的退出清理，原异常继续传播。
- 影响模块：icecream.py:supportTerminalColorsInWindows；colorized打印。
- 兼容边界：不修改Colorama实现；正常非Windows路径保持。
- 正常验收：正常/异常退出init和deinit配对，打印结果保持。
- 边界／错误验收：init自身失败、嵌套调用、关闭流与清理错误不能无说明掩盖原异常；mock证据与实机分开。
- 原生回归：tests/test_icecream.py；独立平台mock验证。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．复用计时器可安全嵌套（增强）

- 来源／实际场景：Timer._enter_time单值；同一timer对象两层with实测。
- 原版现状：内层退出清空状态，外层RuntimeError。
- 用户交付：为显式复用Timer维护独立进入状态，支持嵌套并提供明确并发限制。
- 影响模块：icecream.py:Timer.__enter__/__exit__。
- 兼容边界：原顺序复用与ic.timer每次新实例保持；不把同一字段跨线程共享当作隔离。
- 正常验收：受控时钟下内外分别得到完整正确耗时。
- 边界／错误验收：未进入就退出、异常嵌套、disabled模式、重复退出和跨任务共享有明确规则。
- 原生回归：tests/test_icecream.py:Timer相关用例。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．异步函数计量 await 执行区间（增强）

- 来源／实际场景：Timer.__call__同步wrapper；async原生事件顺序观察。
- 原版现状：计时消息在body-start前就输出，仅量创建coroutine时间。
- 用户交付：识别async def，await后才输出时长并返回真实值；异常同样收口。
- 影响模块：icecream.py:Timer.__call__。
- 兼容边界：同步函数/metadata保持；首版不自动包装任意返回Awaitable的普通函数或异步生成器。
- 正常验收：协程执行完后才输出timer信息，返回7保持。
- 边界／错误验收：取消、await抛错、递归/嵌套计时和disabled不泄漏未await协程。
- 原生回归：tests/test_icecream.py；asyncio原生场景。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．调试对象 repr 失败可选择降级（增强）

- 来源／实际场景：safe_pformat只捕获TypeError；BadRepr实测RuntimeError逃逸。
- 原版现状：ic调用可因用户对象repr出错中断原程序。
- 用户交付：增加opt-in safe_format，输出类型和格式失败标记并继续保持实参返回。
- 影响模块：icecream.py:safe_pformat/_constructArgumentOutput。
- 兼容边界：默认严格异常策略是否保留需显式配置；不捕获KeyboardInterrupt/SystemExit。
- 正常验收：坏repr对象可调试而原业务继续，正常repr无变化。
- 边界／错误验收：repr递归、格式器返回非str、嵌套对象、fallback自己报错有最终有界结果。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．配置校验后整体应用（增强）

- 来源／实际场景：configureOutput(prefix=NEW,outputFunction=123)真实调用。
- 原版现状：非法callback被接受，之后TypeError且prefix已经改变。
- 用户交付：公开配置先验证所有字段，再一起生效；错误不留下半份配置。
- 影响模块：icecream.py:IceCreamDebugger.configureOutput/__init__。
- 兼容边界：保持Sentinel.absent和合法自定义callable；不在验证时执行用户prefix函数。
- 正常验收：合法组合一次生效，非法callback不改变任何旧字段。
- 边界／错误验收：bool/整数行宽、空prefix、错误返回类型、未知键与无参数错误保持明确。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．作用域内临时配置（增强）

- 来源／实际场景：[上游#125](https://github.com/gruns/icecream/issues/125)，当前只有永久enable/disable/configure。
- 原版现状：暂无公开配置上下文，调用者需手动保存字段并finally恢复。
- 用户交付：提供configured/disabled上下文，进入时派生配置，退出/异常恢复，支持嵌套。
- 影响模块：icecream.py:Debugger配置读取与上下文。
- 兼容边界：原永久配置保持；并发隔离采用明确ContextVar或独立实例方案，不能临时改共享全局后声称线程安全。
- 正常验收：嵌套改变prefix/启用状态只影响对应作用域。
- 边界／错误验收：异常、异步任务交错、多个Debugger和格式回调中的重入不串配置。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：07。

### 09．按模块/调用位置过滤输出（增强）

- 来源／实际场景：[上游#178](https://github.com/gruns/icecream/issues/178)；enabled只有全局布尔。
- 原版现状：只能开关整个Debugger，不能只看目标模块。
- 用户交付：增加显式过滤器接收模块/文件/函数元数据，在昂贵格式前判断是否输出。
- 影响模块：icecream.py:Debugger.__call__与调用上下文。
- 兼容边界：默认全部输出，过滤不改返回值；不解析/执行任意配置表达式。
- 正常验收：只允许模块A时B静默，表达式值仍只求值一次。
- 边界／错误验收：过滤器报错策略、动态exec缺源码、同名模块、递归调用与作用域配置组合明确。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．限定类名和嵌套函数上下文（增强）

- 来源／实际场景：[上游#174](https://github.com/gruns/icecream/issues/174)、[#119](https://github.com/gruns/icecream/issues/119)；Example.method实测。
- 原版现状：只显示method()，不同类同名方法难区分。
- 用户交付：可选上下文qualname模式显示Class.method/outer.inner，保留文件行号。
- 影响模块：icecream.py:_getContext/_formatContext。
- 兼容边界：默认简短函数名保持；不为取类名调用self属性或descriptor。
- 正常验收：两个类同名方法输出可区分，静态/类方法正确。
- 边界／错误验收：闭包、lambda、__call__、动态exec和无qualname运行时有稳定fallback。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．单次调用传格式选项（增强）

- 来源／实际场景：[上游#221](https://github.com/gruns/icecream/issues/221)，format短数组参数被拒。
- 原版现状：__call__/format只收位置值，无法局部传formatter选项。
- 用户交付：增加明确format_options通道，将选项传给对应格式器而非调试对象。
- 影响模块：icecream.py:Debugger.__call__/format；argumentToString分发。
- 兼容边界：默认调用与返回值不变；不要用任意kwargs与“命名调试值”混淆。
- 正常验收：同一对象本次短摘要下次详细，无永久配置污染。
- 边界／错误验收：不支持的选项、singledispatch多类型、回调旧签名和禁用路径清楚处理。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．可选颜色环境策略（增强）

- 来源／实际场景：合成TTY+NO_COLOR=1仍有ANSI；已有noColor是手工设置。
- 原版现状：仅根据noColor和isatty，环境不能统一关闭/强制颜色。
- 用户交付：增加显式auto/off环境策略，NO_COLOR/FORCE_COLOR按确定优先级应用到内置输出器。
- 影响模块：icecream.py:colorizedStderrPrint/colorizedStdoutPrint/配置。
- 兼容边界：显式noColor和自定义outputFunction优先；不改argToString内容或Colorama全局。
- 正常验收：合成TTY在NO_COLOR时无ANSI，显式force可按策略保留。
- 边界／错误验收：空环境值、冲突变量、非TTY、无isatty流、异常恢复和stdout/stderr分别验证。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：07。

### 13．关闭上下文时跳过多余检查（增强）

- 来源／实际场景：[上游#246](https://github.com/gruns/icecream/issues/246)与100次原生计数。
- 原版现状：includeContext=False且有参数，100次仍执行100次_getContext。
- 用户交付：只在输出需要上下文/过滤确有需求时执行昂贵上下文检查，保持源码表达式提取。
- 影响模块：icecream.py:_format/_formatContext/_getContext。
- 兼容边界：无参数ic()仍显示上下文/时间；不缓存到过期源文件而错误标注。
- 正常验收：关闭上下文的普通参数调用不查_getContext且输出等价，微基准记录成本变化。
- 边界／错误验收：启用上下文、过滤器、prefix回调、动态源码变化和调试器环境不错误复用。
- 原生回归：tests/test_icecream.py；受控调用计数与微基准。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．结构化调试事件与 JSON 输出（增强）

- 来源／实际场景：自动化调试采集场景；format只返回展示字符串。
- 原版现状：无公开事件对象，JSON化展示字符串会丢实参/来源结构。
- 用户交付：提供format_event与JSON输出器，字段含来源、表达式、格式化值和明确序列化策略。
- 影响模块：icecream.py格式构造与输出协议；新增事件类型。
- 兼容边界：普通字符串outputFunction保持；不默认序列化对象所有私有字段。
- 正常验收：多个参数与source元数据可被JSON读取，顺序和类型标签稳定。
- 边界／错误验收：缺源码、自定义对象、不可序列化值、循环及大小上限明确，默认不转储环境变量。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：01。

### 15．标准 logging 适配器（增强）

- 来源／实际场景：[上游#146](https://github.com/gruns/icecream/issues/146)、[#188](https://github.com/gruns/icecream/issues/188)；现有callback仅收str。
- 原版现状：可手工接logging.debug但失去原调用来源且禁用日志仍先格式化。
- 用户交付：提供logging输出/调试适配器，正确携带调用来源并先检查level是否启用。
- 影响模块：新增标准库logging适配模块；Debugger调用入口。
- 兼容边界：不建立日志服务/新logger框架；保持默认stderr与ic返回值。
- 正常验收：日志记录filename/funcName/line属于用户调用，level关闭时不调用repr。
- 边界／错误验收：handler格式失败、多个logger、stacklevel、异常/递归日志与非字符串prefix清楚处理。
- 原生回归：tests/test_icecream.py；独立LogRecord观测。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．函数参数/返回值跟踪装饰器（增强）

- 来源／实际场景：[上游#32](https://github.com/gruns/icecream/issues/32)、[#57](https://github.com/gruns/icecream/issues/57)；ic(function)当前只返回原函数。
- 原版现状：普通ic检查函数并透传，之后调用不再输出参数/结果；Timer只有时长。
- 用户交付：新增显式trace装饰器记录调用参数与返回/异常，函数名为真实被包裹函数。
- 影响模块：icecream.py新增跟踪入口；functools包装。
- 兼容边界：不把现有ic(function)悄悄改成装饰；MVP同步函数，异步另明确透传策略。
- 正常验收：函数多次调用分别输出绑定参数和返回值，metadata/返回保持。
- 边界／错误验收：默认参数、位置专用/*args/**kwargs、递归、异常和disabled不重复执行函数。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．可配置输出预算与摘要（增强）

- 来源／实际场景：[上游#220](https://github.com/gruns/icecream/issues/220)长字符串；10000字符输出10019。
- 原版现状：lineWrapWidth只折行，不限制总量。
- 用户交付：新增每值/整事件的字符与深度预算，截断明确标出原长度/省略量。
- 影响模块：icecream.py:argumentToString/safe_pformat/_constructArgumentOutput。
- 兼容边界：默认不限制可保持；不为长度统计消费任意generator或执行属性。
- 正常验收：显式预算下长字符串/容器输出有界且短值不变。
- 边界／错误验收：Unicode边界、循环容器、超深、自定义repr超长、多参数总预算和可视字符串组合稳定。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．受管理的文件输出（增强）

- 来源／实际场景：[上游#31](https://github.com/gruns/icecream/issues/31)；已有use_stdout/use_stderr无use_file。
- 原版现状：用户需自行开/关文件并补换行，outputFunction只接单str。
- 用户交付：提供明确文件输出上下文/句柄，支持UTF-8、追加/覆盖策略、每事件换行及关闭。
- 影响模块：新增文件输出辅助模块；Debugger输出配置。
- 兼容边界：不自动写默认路径，不改变自定义callback所有权；外传流与自开文件区分。
- 正常验收：两次ic输出两条完整记录，异常退出也关闭自开句柄。
- 边界／错误验收：路径缺失/权限/编码错误、写后切回stderr、外部流不被误关、并发事件不交错。
- 原生回归：tests/test_icecream.py；真实临时文件读回。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．显式对象字段检查（增强）

- 来源／实际场景：[上游#109](https://github.com/gruns/icecream/issues/109)，原默认仅对象repr。
- 原版现状：没有字段检查入口，普通对象只显示地址。
- 用户交付：新增inspect辅助入口，可列实例__dict__/已声明slots，默认不求值property或任意descriptor。
- 影响模块：新增对象检查辅助；argumentToString注册与Debugger。
- 兼容边界：普通ic(obj)保持；私有字段/敏感字段过滤显式，用户同意才调用descriptor。
- 正常验收：含value=7的对象显示字段，dangerous属性从未被调用。
- 边界／错误验收：slots/无dict/递归对象、字段遮蔽、访问异常与预算受控，不读取全局环境。
- 原生回归：tests/test_icecream.py。
- 实际功能依赖：17。

### 20．可撤销且有归属的 builtin 安装（增强）

- 来源／实际场景：builtins.py:install/uninstall实际合成名字碰撞。
- 原版现状：install返回None；覆盖已有值后uninstall删除该名字，旧值丢失。
- 用户交付：提供受管理安装句柄/上下文，记录旧值，退出仅撤销仍属于自己的安装。
- 影响模块：builtins.py:install/uninstall及新句柄。
- 兼容边界：旧显式覆盖模式需保持或通过参数选择；绝不修改print等真实builtin做研究。
- 正常验收：合成已有名字在退出后恢复，原本不存在的名字移除。
- 边界／错误验收：重复/嵌套安装、别的库中途替换、异常退出、二次撤销与非法名称明确不越权覆盖。
- 原生回归：tests/test_install.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

已经支持源不可见时只显示值并发warning、字面参数不重复显示表达式、noColor、use_stdout/use_stderr、lineWrapWidth、singledispatch注册/注销、同步Timer、禁用后原样返回值和自定义outputFunction；这些不能照旧issue重复计步。没有计划建立新的日志服务、异步发送队列或通用日志框架；logging仅适配标准库。源码中英文注释保留，本轮未改上游。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
