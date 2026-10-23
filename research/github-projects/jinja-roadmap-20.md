# Jinja：二十步真实工程迭代路线

固定 [pallets/jinja@5ef70112a1ff19c05324ff889dd30405b1002044](https://github.com/pallets/jinja/tree/5ef70112a1ff19c05324ff889dd30405b1002044)，原生证据见 [单仓审查](./jinja.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．urlencode接受标准Mapping协议

- **类型与来源**：修复；[官方#2269](https://github.com/pallets/jinja/issues/2269) 与固定源码/observe.py。
- **原版现状与收益**：UserDict两字符键被当pair拆成A=a&B=b，单字符键会解包异常；类型标注本来声明Mapping。
- **交付及模块**：用Mapping协议取items，保持pair iterable与字符串路径的区别；filters.do_urlencode。
- **兼容与依赖**：普通dict、顺序pair、重复query键和既有URL转义规则保持；步骤依赖：无。
- **正常验收**：UserDict与等价dict生成Aa=PersonA%40123.com等同结果。
- **异常／边界验收**：单字符/Unicode键、只读Mapping、空mapping、非法pair维持明确错误。
- **原生回归**：tests/test_filters.py。

## 02．未定义子属性不再冒充已转义HTML

- **类型与来源**：修复；[官方#2244](https://github.com/pallets/jinja/issues/2244) 与固定源码/observe.py。
- **原版现状与收益**：ChainableUndefined.__html__使parent.child is escaped=True，但同值is defined=False。
- **交付及模块**：明确escaped测试对Undefined的语义，避免错误选择HTML分支；tests.test_escaped、runtime.ChainableUndefined。
- **兼容与依赖**：真正Markup和合法__html__对象仍视为escaped，safe/默认Undefined行为不得静默破坏；步骤依赖：无。
- **正常验收**：空parent选择descriptionHtml后备值；Markup正对照继续True。
- **异常／边界验收**：多层链、显式None、StrictUndefined、沙箱和autoescape开关。
- **原生回归**：tests/test_tests.py、tests/test_runtime.py、tests/test_security.py。

## 03．indent保持空行策略与环境换行

- **类型与来源**：修复；[官方#2176](https://github.com/pallets/jinja/issues/2176)、[官方#2016](https://github.com/pallets/jinja/issues/2016) 与固定源码/observe.py。
- **原版现状与收益**：空输入first=True产生4空格；CRLF环境的indent实际输出LF。两者合并为完整文本布局修复。
- **交付及模块**：在保持Markup属性下统一首行/空行与newline_sequence策略；filters.do_indent、Environment传入方式。
- **兼容与依赖**：默认LF非空文本与width字符串保持；first不能覆盖blank=False；明确原生filter直调默认LF；步骤依赖：无。
- **正常验收**：空块保持空串，CRLF宏缩进后全部行尾仍CRLF。
- **异常／边界验收**：仅换行、首行空白、blank=True、首尾空行、Markup与自定义缩进串。
- **原生回归**：tests/test_filters.py、tests/test_api.py。

## 04．slice仅补足较短列

- **类型与来源**：修复；[官方#2118](https://github.com/pallets/jinja/issues/2118) 与固定源码/observe.py。
- **原版现状与收益**：4个元素slice(4,foo)产生四个额外foo，整除时没有短列仍填充。
- **交付及模块**：按实际目标列长决定补值，保留列顺序与生成器入口；filters.sync_do_slice／do_slice。
- **兼容与依赖**：未提供fill_with与非整除的既有布局保持；非法列数给既定受控错误；步骤依赖：无。
- **正常验收**：4/4只得[[1],[2],[3],[4]]，5/3短列补到同长。
- **异常／边界验收**：空序列、列数大于元素、slices为0/负数及async iterable。
- **原生回归**：tests/test_filters.py、tests/test_async_filters.py。

## 05．map显式None默认值可以替换缺失字段

- **类型与来源**：修复；[官方#2165](https://github.com/pallets/jinja/issues/2165) 与固定源码/observe.py。
- **原版现状与收益**：make_attrgetter用None表示未提供default，实测default=none仍返回Undefined。
- **交付及模块**：引入缺省哨兵，区分缺省与显式None并贯通map和共享getter；filters.make_attrgetter／prepare_map。
- **兼容与依赖**：未指定default继续Undefined；已有非None默认值保持，不把实际None字段当缺失；步骤依赖：无。
- **正常验收**：map(attribute=foo,default=none)对缺key输出真实None。
- **异常／边界验收**：嵌套缺父属性、StrictUndefined、默认值为False/0/空串与已有None字段。
- **原生回归**：tests/test_filters.py、tests/test_async_filters.py。

## 06．宏内无context include输出实际内容

- **类型与来源**：修复；[官方#2108](https://github.com/pallets/jinja/issues/2108) 与固定源码/observe.py。
- **原版现状与收益**：同步宏内include without context实测返回generator repr；编译器无context同步分支直接yield from，越过宏buffer。
- **交付及模块**：在宏/捕获块中按当前frame输出策略写入include内容；compiler.CodeGenerator.visit_Include、frame buffer。
- **兼容与依赖**：模板顶层include仍流式，without context仍隔离调用变量，不改成自动with context；步骤依赖：无。
- **正常验收**：宏内include静态foo得到foo，外层宏正常拼接。
- **异常／边界验收**：嵌套宏、filter/capture块、ignore missing、autoescape与async渲染一致。
- **原生回归**：tests/test_imports.py、tests/test_core_tags.py、tests/test_async.py。

## 07．异步map结果可直接排序

- **类型与来源**：修复；[官方#2081](https://github.com/pallets/jinja/issues/2081) 与固定源码/observe.py。
- **原版现状与收益**：enable_async模板中map生成async_generator，do_sort调用sorted触发TypeError；同步正对照成功。
- **交付及模块**：为sort提供async_variant，在异步模板中有界契约地收集输入再排序；filters.do_sort、async_utils.auto_to_list。
- **兼容与依赖**：sort本来必须物化全体，不伪装流式；同步稳定排序、reverse、多属性语义保持；步骤依赖：无。
- **正常验收**：相同letters在sync/async渲染都为[a,d]，无需用户加list。
- **异常／边界验收**：空async序列、生成器异常/关闭、不可比较键、大小写和多属性稳定排序。
- **原生回归**：tests/test_async_filters.py、tests/test_filters.py。

## 08．meta准确识别各分支都赋值的局部量

- **类型与来源**：修复；[官方#2069](https://github.com/pallets/jinja/issues/2069) 与固定源码/observe.py。
- **原版现状与收益**：if/else全部赋output之后引用，find_undeclared_variables仍返回control和output。
- **交付及模块**：符号分支合并区分必定赋值与可能回读上下文变量；idtracking.Symbols.branch_update、meta.TrackingCodeGenerator。
- **兼容与依赖**：缺else或有分支未赋值仍保守报告，不把任意赋值都认成全局已定义；步骤依赖：无。
- **正常验收**：全部if/elif/else赋output只报告control。
- **异常／边界验收**：嵌套分支、分支先读后写、循环/宏作用域、缺else与短路变量。
- **原生回归**：tests/test_idtracking.py、tests/test_api.py。

## 09．负数幂运行时与常量折叠一致

- **类型与来源**：修复；[官方#1720](https://github.com/pallets/jinja/issues/1720) 与固定源码/observe.py。
- **原版现状与收益**：-1**x在x=2输出-1，同结构常量-1**2却为1，显式(-1)**x仍-1。
- **交付及模块**：生成Python时按AST保留负常量操作数分组，统一优化与运行时；compiler._make_binop／visit_Const、nodes.Pow。
- **兼容与依赖**：保留Jinja已记录的幂左结合；#1722的64不被改成Python512。不得仅特判-1；步骤依赖：无。
- **正常验收**：x=2时负底数幂与常量折叠一致，优化开关结果一致。
- **异常／边界验收**：正负底数、奇偶/负/零指数、括号、sandbox拦截及动态变量两侧。
- **原生回归**：tests/test_lexnparse.py、tests/test_compile.py、tests/test_security.py。

## 10．模板流dump支持PathLike目标

- **类型与来源**：增强；[官方#2039](https://github.com/pallets/jinja/issues/2039) 与固定源码/observe.py。
- **原版现状与收益**：TemplateStream.dump只识别str文件名，Path实际被当stream并AttributeError。
- **交付及模块**：用os.fspath支持标准路径协议，保留调用者文件流所有权；environment.TemplateStream.dump。
- **兼容与依赖**：现有str默认UTF8、显式encoding与file-like保持；不把所有对象转str；步骤依赖：无。
- **正常验收**：Path输出完整中文模板到临时文件，等价str输出字节一致。
- **异常／边界验收**：自定义PathLike、坏fspath返回类型、写失败、buffer模式与调用者stream不关闭。
- **原生回归**：tests/test_api.py。

## 11．属性路径支持序列负索引

- **类型与来源**：增强；[官方#2116](https://github.com/pallets/jinja/issues/2116) 与固定源码/observe.py。
- **原版现状与收益**：_prepare_attribute_parts只把isdigit片段转int；sort(attribute=-1字符串)未按最后元素排序。
- **交付及模块**：显式定义带符号整数路径片段并贯通共享属性getter；filters._prepare_attribute_parts／make_multi_attrgetter。
- **兼容与依赖**：现有正整数和点路径保持；字符串键-1的迁移须有转义/替代访问说明，不任意接受浮点；步骤依赖：无。
- **正常验收**：元组列表按最后元素排序，嵌套rows.-1.name可用于map。
- **异常／边界验收**：越界、空列表、混合负索引/字符串key、default与sandbox访问边界。
- **原生回归**：tests/test_filters.py、tests/test_async_filters.py。

## 12．宏签名声明仅关键字参数

- **类型与来源**：增强；[官方#1992](https://github.com/pallets/jinja/issues/1992) 与固定源码/observe.py。
- **原版现状与收益**：parse_signature仅普通参数/default，无裸星号；调用位置绑定不限制。
- **交付及模块**：允许macro foo(a,*,label,kind=...)，宏运行时检查必需关键字与非法位置实参；parser.parse_signature、nodes.Macro、compiler.macro_body、runtime.Macro。
- **兼容与依赖**：旧宏签名和varargs/kwargs惯例保持；不附带自定义*args重命名新语言；步骤依赖：无。
- **正常验收**：命名参数调用成功，参数顺序调整不改变调用方意义。
- **异常／边界验收**：缺必填key、重复赋值、位置参数超限、caller/kwargs、async宏。
- **原生回归**：tests/test_core_tags.py、tests/test_imports.py、tests/test_async.py。

## 13．include显式传递局部参数

- **类型与来源**：增强；[官方#241](https://github.com/pallets/jinja/issues/241) 与固定源码/observe.py。
- **原版现状与收益**：include只能with/without context；include child with x=1实际语法错误。
- **交付及模块**：增加明确参数语法并构造仅本次include的派生context；parser.parse_include、nodes.Include、compiler.visit_Include。
- **兼容与依赖**：已有with context语法保持，显式值只覆盖include局部且不回写父context；步骤依赖：06。
- **正常验收**：同一组件include两次传不同title，各自输出且父title不变。
- **异常／边界验收**：重复key、Undefined、ignore missing、without context组合、嵌套/asyncinclude。
- **原生回归**：tests/test_imports.py、tests/test_core_tags.py。

## 14．宏导入支持候选模板回退

- **类型与来源**：增强；[官方#1862](https://github.com/pallets/jinja/issues/1862) 与固定源码/observe.py。
- **原版现状与收益**：include已有候选列表，但import列表实测把list放缓存key而TypeError。
- **交付及模块**：import/from导入接受有序候选，用现有select_template语义选择并保留TemplateNotFound上下文；compiler.visit_Import／visit_FromImport、Environment.get_or_select_template。
- **兼容与依赖**：普通字符串导入缓存和with context行为保持；首个存在但语法错误不能被吞掉转下个；步骤依赖：无。
- **正常验收**：缺失主题宏时回退默认宏，选中项中的调用正常。
- **异常／边界验收**：全部缺失、空列表、首个语法错、from缺宏、async与import缓存。
- **原生回归**：tests/test_imports.py、tests/test_loader.py。

## 15．原生异步模板源码加载协议

- **类型与来源**：增强；[官方#1304](https://github.com/pallets/jinja/issues/1304) 与固定源码/observe.py。
- **原版现状与收益**：渲染支持async但_load_template/BaseLoader.load同步调用；awaitable FunctionLoader结果不受支持。
- **交付及模块**：新增显式async加载入口，extends/include/import在async编译路径await对应协议；loaders.BaseLoader／FunctionLoader、Environment加载器、compiler导入指令。
- **兼容与依赖**：同步loader桥接不强迫线程化；sync环境遇async-only loader明确拒绝；不阻塞event loop去run asyncio；步骤依赖：无。
- **正常验收**：用合成async内存loader渲染含继承/include的模板，计时证明等待期间其他协程可运行。
- **异常／边界验收**：并发同名加载/缓存、取消、缺模板、loader异常与同步入口误用。
- **原生回归**：tests/test_async.py、tests/test_loader.py、tests/test_bytecode_cache.py。

## 16．通用资源树模板加载器

- **类型与来源**：增强；[官方#2035](https://github.com/pallets/jinja/issues/2035)、[官方#1978](https://github.com/pallets/jinja/issues/1978) 与固定源码/observe.py。
- **原版现状与收益**：FileSystemLoader要求os.fspath，PackageLoader手工区分目录/zipimporter，不能通用Traversable资源树。
- **交付及模块**：增加ResourcesLoader接收Traversable根并读源码/list_templates，PackageLoader可显式复用；loaders.PackageLoader／FileSystemLoader及新ResourcesLoader。
- **兼容与依赖**：磁盘loader优先级与followlinks保持；未知资源无mtime时明确定义reload，不假装全部ZIP动态更新；步骤依赖：无。
- **正常验收**：同一模板树在目录与合成Traversable/zip资源中渲染及枚举一致。
- **异常／边界验收**：命名空间多根冲突、路径穿越、坏编码、不支持list或reload的资源清晰报错。
- **原生回归**：tests/test_loader.py、tests/test_regression.py。

## 17．记录本次渲染实际模板依赖

- **类型与来源**：增强；[官方#1775](https://github.com/pallets/jinja/issues/1775) 与固定源码/observe.py。
- **原版现状与收益**：meta静态分析对动态include返回None，不能告诉构建器实际选中的模板链。
- **交付及模块**：增加opt-in逐render依赖collector，记录实际extends/include/import选择及父边；Environment加载入口、runtime.Context、meta辅助结构。
- **兼容与依赖**：静态meta API继续保守；记录限定当前render，不全局共享，不记录模板变量值；步骤依赖：无。
- **正常验收**：动态主题模板返回main→chosen→base实际链用于增量构建。
- **异常／边界验收**：缓存命中、fallback候选、include missing、递归/重复边与并发async隔离。
- **原生回归**：tests/test_loader.py、tests/test_inheritance.py、tests/test_async.py。

## 18．按选项保留模板注释AST

- **类型与来源**：增强；[官方#1967](https://github.com/pallets/jinja/issues/1967) 与固定源码/observe.py。
- **原版现状与收益**：lexer过滤comment token，parse后的a注释b仅Output，模板文档生成器拿不到注释归属。
- **交付及模块**：parse显式preserve_comments输出Comment节点、原文和位置，编译时作为无输出节点处理；lexer过滤策略、parser、nodes.Comment、compiler visitor。
- **兼容与依赖**：默认AST与渲染保持；注释仍不出现在最终HTML，不能把注释当可执行模板；步骤依赖：无。
- **正常验收**：分析器能取宏前文档注释及位置，编译/渲染产物与未保留模式一致。
- **异常／边界验收**：多行/空注释、空白裁剪标记、原始区块、line_comment及未知visitor兼容。
- **原生回归**：tests/test_lexnparse.py、tests/test_nodes.py、tests/test_ext.py。

## 19．表达式提供精确源码位置与生成映射

- **类型与来源**：增强；[官方#2133](https://github.com/pallets/jinja/issues/2133)、[官方#408](https://github.com/pallets/jinja/issues/408) 与固定源码/observe.py。
- **原版现状与收益**：Node只有lineno/environment，debug_info只有行对映；同一行多个表达式难定位编辑器诊断/覆盖。
- **交付及模块**：增量记录token/AST列起止，提供稳定的生成代码行到模板span映射；lexer.Token、nodes.Node、parser位置传播、compiler.debug_info、debug模块。
- **兼容与依赖**：原lineno/get_corresponding_lineno不移除；扩展构造无列位置仍可工作，未知span明确None；步骤依赖：无。
- **正常验收**：同一行两个表达式失败分别定位正确列；覆盖工具可查生成行的模板span。
- **异常／边界验收**：Unicode列定义、CRLF、trim标记、多行字符串、扩展节点和预编译模板。
- **原生回归**：tests/test_lexnparse.py、tests/test_debug.py、tests/test_compile.py。

## 20．保留完整访问路径的调试未定义类型

- **类型与来源**：增强；[官方#1871](https://github.com/pallets/jinja/issues/1871) 与固定源码/observe.py。
- **原版现状与收益**：DebugUndefined缺根env时访问env.val直接抛错；已有ChainableUndefined可链但只输出空串。
- **交付及模块**：新增可选PathDebugUndefined记录attr/item路径并输出可识别占位符；runtime.Undefined子类、Environment.getattr／getitem交接。
- **兼容与依赖**：不静默改变StrictUndefined或现有DebugUndefined；调试输出仍受autoescape，不能把链结果当真实HTML；步骤依赖：02。
- **正常验收**：env.val和rows[2].name缺失时输出完整路径占位，已有值正常输出。
- **异常／边界验收**：dunder探测继续AttributeError、对象getter真实异常、键含引号/Unicode、copy/pickle及safe测试。
- **原生回归**：tests/test_runtime.py、tests/test_api.py、tests/test_tests.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
