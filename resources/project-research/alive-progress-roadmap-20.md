# alive-progress：二十步真实工程路线

固定 [rsalmei/alive-progress@69d9bf0aba6276e2434a3a595cceca55040d64d7](https://github.com/rsalmei/alive-progress/tree/69d9bf0aba6276e2434a3a595cceca55040d64d7)。原生基线 563 通过、0 跳过；范围和限制见 [单仓审查](./alive-progress.md)。类型计数：{"修复": 3, "增强": 17}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．按是否提供调用结束回调（修复）

- 来源／实际场景：[上游#331](https://github.com/rsalmei/alive-progress/issues/331)与FalseFinalizer实测。
- 原版现状：合法callable的__bool__返回False，迭代结束calls仍为空。
- 用户交付：finalize只以是否为None区分缺省，已提供的合法调用对象必执行一次。
- 影响模块：core/progress.py:__AliveBarIteratorAdapter.__iter__。
- 兼容边界：默认None和普通函数保持；不执行bool来判断可调用性。
- 正常验收：两个元素正常耗尽后假值finalize收到current=2。
- 边界／错误验收：空输入、True/False callable、回调抛错与非callable按明确校验处理，不重复调用。
- 原生回归：tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．配置阶段验证嵌套格式和转换符（修复）

- 来源／实际场景：[上游#328](https://github.com/rsalmei/alive-progress/issues/328)；_format_input_factory实测。
- 原版现状：{count:{missing}}、{count!z}配置成功，格式化才KeyError/ValueError。
- 用户交付：递归检查format_spec引用字段及转换符，启动前抛有配置键上下文的ValueError。
- 影响模块：core/configuration.py:_format_input_factory；所有格式widget。
- 兼容边界：保留纯文本、转义花括号与合法s/r/a；不承诺静态解决所有值依赖格式错误。
- 正常验收：合法嵌套动态宽度和原默认模板正常。
- 边界／错误验收：未知嵌套字段、非法转换、嵌套过深、未闭括号及不能用于该widget的字段在配置阶段失败。
- 原生回归：tests/core/test_configuration.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．未启动迭代器遵守属性探测协议（修复）

- 来源／实际场景：[上游#327](https://github.com/rsalmei/alive-progress/issues/327)；hasattr/inspect.unwrap实际抛错。
- 原版现状：未知__wrapped__也抛UserWarning，Python内省无法正常探测。
- 用户交付：未知属性抛AttributeError；确有进度操作在未开始时保留明确配置提示。
- 影响模块：core/progress.py:__AliveBarIteratorAdapter.__getattr__；句柄公开属性定义。
- 兼容边界：不吞掉真实property内部异常；开始/结束后的转发语义保持。
- 正常验收：hasattr未知属性为False、inspect.unwrap返回原对象。
- 边界／错误验收：__rich__/__wrapped__等协议探测、已知text/receipt、开始后缺失属性和重复迭代覆盖。
- 原生回归：tests/core/test_progress.py；tests/core/test_progress_util.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．字节兼容输出可跨写片段解码（增强）

- 来源／实际场景：core/hook_manager.py:write有bytes兼容；UTF-8拆分实测。
- 原版现状：每次part.decode，拆开的中文字节第一段即UnicodeDecodeError；完整字节串可解码。
- 用户交付：为明确支持的字节输出增加增量解码并按流隔离，结尾处理不完整序列有明确策略。
- 影响模块：core/hook_manager.py:write/flush/uninstall。
- 兼容边界：普通TextIO字符串和click.echo保持；首版固定已声明ENCODING，不自动猜测编码。
- 正常验收：分两次写完中文后打印一条正确的带进度信息。
- 边界／错误验收：不同流交错、非法字节、退出时半字符、flush和换行策略不丢数据/串解码器。
- 原生回归：tests/core/test_hook_manager.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．可选近期吞吐和ETA估算（增强）

- 来源／实际场景：[上游#247](https://github.com/rsalmei/alive-progress/issues/247)；受控5小时60/s后20/s。
- 原版现状：平滑的是count/total_elapsed，变慢一秒后仍59.9993/s。
- 用户交付：增加可选差分/时间窗口估算器，使阶段速率变化在规定窗口内反映到ETA。
- 影响模块：core/progress.py:main_update_hook；utils/timing.py估算器；配置。
- 兼容边界：保留累计平均策略作兼容选项；skipped不混入处理速率，pause不计停机时间。
- 正常验收：稳定60/s切20/s后在窗口内收敛，预测完成时间合理。
- 边界／错误验收：零/回退增量、时钟边界、长停顿、跳过恢复、低频刷新及零速率不会NaN/除零。
- 原生回归：tests/utils/test_timing.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．运行中发现或修改总工作量（增强）

- 来源／实际场景：README To do的unknown转auto与动态total；句柄无set_total/reset。
- 原版现状：total捕获在闭包和gen_eta，运行中没有公开修改入口。
- 用户交付：统一增加重新定量接口，未知转已知、已知增减都同步更新百分比/ETA/收据。
- 影响模块：core/progress.py:__alive_bar及__AliveBarHandle；估算器。
- 兼容边界：既有total/手动模式保持；已知0与未知的表示需明确定义，不能仅赋一个无效动态属性。
- 正常验收：爬取时先未知，发现总量10后已处理3表现为3/10，再增到12正确。
- 边界／错误验收：总量小于current、非法类型、结束后修改、并发刷新及未知反切不留下旧ETA。
- 原生回归：tests/core/test_progress.py；tests/utils/test_timing.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．单一渲染器管理多条并发进度（增强）

- 来源／实际场景：[上游#20](https://github.com/rsalmei/alive-progress/issues/20)和README To do；真实nested触发明确拒绝。
- 原版现状：全局hook排斥嵌套，只能顺序显示。
- 用户交付：增加显式多进度管理器，共享终端/挂钩，分配独立行与计数句柄。
- 影响模块：core/progress.py、core/hook_manager.py、utils/terminal与多行渲染管理。
- 兼容边界：保留普通alive_bar单条路径；首版仅同进程同输出流，不声称跨进程MPI支持。
- 正常验收：两下载任务独立更新，打印消息出现在进度区域上方，退出恢复流/光标。
- 边界／错误验收：嵌套退出、一个任务失败、终端缩窄、非TTY、动态删除任务和部分初始化失败无残留线程。
- 原生回归：tests/core/test_progress.py；tests/core/test_hook_manager.py；tests/utils/test_cells.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．终端改变宽度时重新分配布局（增强）

- 来源／实际场景：README To do；_create_bars按length=40编译，当前由print_cells硬截断。
- 原版现状：终端cols改变只裁尾部，实际bar仍40格，关键计数可能消失。
- 用户交付：可选自动宽度布局优先保留关键widget，对余宽重编译/缓存条形并正确处理宽字符。
- 影响模块：core/progress.py:_create_bars/alive_repr；utils/cells.py；terminal/tty.py。
- 兼容边界：默认固定length可保留；不每帧无限缓存不同宽度，max_cols仍是回退。
- 正常验收：模拟80→40→100列时条形伸缩、计数可见且宽度从不溢出。
- 边界／错误验收：极窄/0列、宽字title、双行/多条、resize抖动与最终收据宽度策略明确。
- 原生回归：tests/utils/test_cells.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．保留多行实时状态区域（增强）

- 来源／实际场景：[上游#188](https://github.com/rsalmei/alive-progress/issues/188)；dual_line文本first
second实测。
- 原版现状：sanitize把换行变空格，dual_line仅支持一个额外行。
- 用户交付：增加显式多行状态，按行计算单元格和光标移动，更新行数缩减能清除旧行。
- 影响模块：core/progress.py:set_text/alive_repr；utils/cells.py与terminal实现。
- 兼容边界：默认text单行/dual_line保持；非TTY最终一次输出，无无界刷新日志。
- 正常验收：3行统计更新成2行，旧第三行消失，外部print不中断布局。
- 边界／错误验收：CRLF、空行、宽字、极长行、异常退出与嵌套多条占用行数正确。
- 原生回归：tests/utils/test_cells.py；tests/core/test_progress.py；tests/core/test_hook_manager.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．对着色片段保持可见单元格宽度（增强）

- 来源／实际场景：[上游#49](https://github.com/rsalmei/alive-progress/issues/49)和README To do；SGR+A+reset被计10格。
- 原版现状：动画/标题直接含ANSI时转义字符被当作可见格。
- 用户交付：引入明确的带样式片段，SGR不占列，裁剪/拼接/反转仍保持样式闭合。
- 影响模块：utils/cells.py、utils/colors.py、animations及progress渲染。
- 兼容边界：纯文本单元格语义保持；首版支持受控SGR颜色，不把任意终端控制序列视为样式。
- 正常验收：红色A宽度1，着色动画经过裁剪仍对齐且结束reset。
- 边界／错误验收：嵌套样式、宽字/ZWJ、被裁断片段、未知序列及非TTY颜色策略确定。
- 原生回归：tests/utils/test_cells.py；tests/animations/test_utils.py；tests/animations/test_bars.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．展示命名分类计数器（增强）

- 来源／实际场景：[上游#71](https://github.com/rsalmei/alive-progress/issues/71)；counters配置当前拒绝。
- 原版现状：只有单一count/processed，分类信息需用户自行拼text。
- 用户交付：增加显式counter更新与widget，成功/过滤等分类独立展示，可选与总进度联动。
- 影响模块：core/configuration.py、core/progress.py句柄/状态/widget。
- 兼容边界：普通bar()不变；不把分类和总数默认相加导致双计数，规则必须显式。
- 正常验收：success=5、filtered=2与总数7一致，收据能看到分类。
- 边界／错误验收：未知名称、负/非整数、顺序稳定、并发更新、移除类别与状态快照有明确约束。
- 原生回归：tests/core/test_configuration.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．运行时调整最终收据组件（增强）

- 来源／实际场景：[上游#297](https://github.com/rsalmei/alive-progress/issues/297)；赋monitor_end=False仍输出2/2。
- 原版现状：动态属性赋值被接受但闭包widget完全不变。
- 用户交付：提供受校验的receipt配置方法，运行/结束前决定最终monitor/elapsed/stats/text显示。
- 影响模块：core/progress.py:_Widget与句柄；configuration验证复用。
- 兼容边界：原构造参数和结束后title/text保持；不允许随意重写只读current等属性。
- 正常验收：运行中显示统计，成功结束后只留自定义标题；失败时可保留统计。
- 边界／错误验收：非法模板不部分应用、结束后按需receipt、并发渲染与无receipt模式正确。
- 原生回归：tests/core/test_progress_util.py；tests/core/test_configuration.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 13．慢任务可显示每项耗时（增强）

- 来源／实际场景：[上游#184](https://github.com/rsalmei/alive-progress/issues/184)；seconds_per_item字段被拒绝。
- 原版现状：支持rate的单位缩放，但没有s/item倒数语义。
- 用户交付：增加明确的速率方向/每项耗时字段，可选按阈值切换并应用单位。
- 影响模块：core/progress.py:rate_text/stats；configuration格式字段。
- 兼容边界：默认item/s和SI/IEC缩放保持；与单位倍率的倒数转换不可混淆。
- 正常验收：0.5item/s显示2.0s/item，2item/s在auto方向显示2item/s。
- 边界／错误验收：零速率、百分比手动模式、微小速率、阶段切换与自定义unit无除零/无穷字符串污染。
- 原生回归：tests/core/test_progress.py；tests/core/test_configuration.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．可选终端窗口进度状态协议（增强）

- 来源／实际场景：[上游#314](https://github.com/rsalmei/alive-progress/issues/314)、[微软官方协议](https://learn.microsoft.com/en-us/windows/terminal/tutorials/progress-bar-sequences)；普通输出无OSC9;4。
- 原版现状：只画文本进度，窗口/任务栏不能同步状态。
- 用户交付：增加显式开启的OSC9;4适配器，发送确定百分比/未知/错误/清除状态。
- 影响模块：utils/terminal新增协议适配；core/progress.py生命周期。
- 兼容边界：默认不开启；非TTY/文件不发控制码；已核对微软官方state 0/1/2/3/4及progress 0..100规范，实施前冻结协议样本。
- 正常验收：已知进度0→50→100对应协议事件，退出发送清除。
- 边界／错误验收：异常/取消、未知总量、百分比越界、多条的聚合规则和不支持终端安全关闭。
- 原生回归：tests/core/test_progress.py；独立终端协议字节观测。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．取得结构化原始进度快照（增强）

- 来源／实际场景：自动化批处理需数值指标；当前rate/eta是str而elapsed为float。
- 原版现状：没有统一只读snapshot，解析显示文本会丢单位/精度。
- 用户交付：公开不可变snapshot，包含current/total/processed/percent/elapsed/rate/eta和状态。
- 影响模块：core/progress.py状态/句柄；新增快照类型。
- 兼容边界：现有文本属性保持；按一次受锁采样得到一致数据，不依赖外部监控服务。
- 正常验收：中途与结束可读数字值，JSON适配不需反解析格式化字符串。
- 边界／错误验收：未知总量用None、无样本速率、暂停/取消/结束后冻结以及多线程读取一致。
- 原生回归：tests/core/test_progress_util.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．消费异步迭代输入并跟踪进度（增强）

- 来源／实际场景：异步网络批处理场景；alive_it(async_generator)实测TypeError。
- 原版现状：仅支持同步iter，暂无alive_ait。
- 用户交付：增加原生异步适配器，async for每项处理后更新，支持异步源的关闭与取消。
- 影响模块：core/progress.py异步适配器与公开__init__.py。
- 兼容边界：同步alive_it不改；不在库内另起事件循环，渲染线程不执行用户协程。
- 正常验收：异步产生1/2，真实await处理完后current=2，返回元素身份不变。
- 边界／错误验收：取消、源异常、提前aclose、空源和异步finalizer的允许范围清楚，资源均恢复。
- 原生回归：tests/core/test_progress.py；asyncio受控场景。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．按每项工作量自动累计进度（增强）

- 来源／实际场景：大小不同文件的迭代场景；weights配置被拒绝。
- 原版现状：手工bar(size)已有，但alive_it固定每项加1。
- 用户交付：增加明确加权迭代入口/weight回调，元素处理后累计实际工作量并显示正确单位。
- 影响模块：core/progress.py:alive_it与适配器；配置/类型。
- 兼容边界：默认每项计数保持；不得先消费生成器计算total，不混淆项数与字节。
- 正常验收：2字节和8字节两项分别使current=2/10、10/10，元素只处理一次。
- 边界／错误验收：零/负/非数值权重、回调异常、未知总权重、提前退出及浮点权重是否支持明确。
- 原生回归：tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．区分成功异常和提前关闭的生命周期回调（增强）

- 来源／实际场景：批处理希望记录失败收据；failing_source实测finalize未调用。
- 原版现状：finalize只在正常耗尽触发且只收bar，异常/关闭没有原因事件。
- 用户交付：保留成功finalize并增加on_finish事件，提供完成/异常/关闭原因及最终快照。
- 影响模块：core/progress.py:迭代器生命周期与上下文收尾；事件类型。
- 兼容边界：不悄改原finalize在失败时触发；原异常优先传播，事件回调错误策略明确。
- 正常验收：成功和源RuntimeError各产生一次正确终态事件，失败不伪装成功。
- 边界／错误验收：consumer抛错/显式close、GeneratorExit、取消、回调自身异常和空源最多一次。
- 原生回归：tests/core/test_progress.py。
- 实际功能依赖：01, 15。

### 19．明确选择打印与日志挂钩范围（增强）

- 来源／实际场景：嵌入程序使用独立file时仍替换全局stdout和自定义logger；enrich_print=False仅关前缀。
- 原版现状：无法仅渲染目标流而保留其他打印/日志对象身份。
- 用户交付：新增print/logging挂钩策略，支持关闭、仅目标流或显式handler集合，并按归属恢复。
- 影响模块：core/configuration.py；core/hook_manager.py:install/uninstall；progress初始化。
- 兼容边界：默认自动挂钩保持；disable仍完全关闭，不把enrich_print复用为新语义。
- 正常验收：独立file+hooks关闭时stdout和无关handler身份不变，目标流正常出收据。
- 边界／错误验收：运行期间新建/替换handler、嵌套管理器、异常初始化和外部接管流不会错误恢复覆盖。
- 原生回归：tests/core/test_hook_manager.py；tests/core/test_configuration.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．局部作用域共享进度配置（增强）

- 来源／实际场景：库函数和应用同时设全局样式的场景；create_config只有set_global/reset。
- 原版现状：每次参数覆盖已有，但无作用域默认值，永久set_global会影响无关调用。
- 用户交付：提供显式配置作用域，作用域内新bar继承，退出恢复，支持异步任务隔离。
- 影响模块：core/configuration.py:create_config/config_handler；上下文默认值读取。
- 兼容边界：set_global永久设置保持；已运行bar的不可变Config不被回写；不能仅临时改共享dict声称隔离。
- 正常验收：外层主题A、内层B、退出仍A，显式bar参数始终优先。
- 边界／错误验收：嵌套异常、异步任务交错、线程边界、reset/set_global交互和多进度管理器规则明确。
- 原生回归：tests/core/test_configuration.py；tests/core/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

已经有自动/未知/手动模式、零和负增量、skipped=True续跑、bar.pause、最终收据与结束后改title/text、单位缩放、rate/eta文本查询、自动禁用非TTY动画、dual_line两行、打印/日志多线程同步及文件输出。它们不重复计步；命名计数器不同于一个总count，近期速率不同于现有累计速度的指数平滑，多行状态不同于固定双行。contrib分发、增加动画皮肤、测试覆盖率或新参数排列不单独计步。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
