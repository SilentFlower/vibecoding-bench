# mistletoe：二十步真实工程路线

固定 [miyuchina/mistletoe@ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7](https://github.com/miyuchina/mistletoe/tree/ebf9ae4e9279f3d8c79b7cf2710f7e73ea6438a7)。原生基线 352 通过、1 跳过；范围和限制见 [单仓审查](./mistletoe.md)。类型计数：{"修复": 10, "增强": 10}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．标题实例保留自己的原内容（修复）

- 来源／实际场景：[上游#212](https://github.com/miyuchina/mistletoe/issues/212)；正确renderer上下文内3标题复现。
- 原版现状：HTML各自正确，但三个Heading.content都读到最后标题Third类属性。
- 用户交付：构造时把自身内容存入实例，后续标题解析不污染已有AST。
- 影响模块：block_token.py:Heading.__init__/start/read；AST导出。
- 兼容边界：保留原始标记内容与children区分，不把渲染后的纯文本冒充源内容。
- 正常验收：First/Second/Third的content分别正确，解析第二文档不回写第一文档。
- 边界／错误验收：空标题、闭合#、行内格式、Setext和repr/AST序列化行为明确。
- 原生回归：test/test_block_token.py；test/test_ast_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．基础渲染器安全处理无子节点叶子（修复）

- 来源／实际场景：[上游#208](https://github.com/miyuchina/mistletoe/issues/208)、#243；a换行b真实调用。
- 原版现状：BaseRenderer.render_line_break交给render_inner，None不可迭代。
- 用户交付：为叶节点定义可预测默认文本/分隔行为，render_inner只递归真实children。
- 影响模块：base_renderer.py默认render_line_break/render_block_code/render_thematic_break。
- 兼容边界：自定义子类覆写优先；不把所有None默认为空而静默丢掉有content的叶子。
- 正常验收：基本renderer对换行、代码内容和普通段落不抛TypeError，保留有意义文本。
- 边界／错误验收：空容器/叶子、自定义token缺字段、硬/软断行、异常子render维持清晰错误。
- 原生回归：test/test_core_tokens.py；test/test_html_renderer.py；新增BaseRenderer回归。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．无可用标题时返回空目录（修复）

- 来源／实际场景：contrib/toc_renderer.py:toc；无标题Document真实IndexError。
- 原版现状：items[0]访问空列表，无标题或全部过滤即失败。
- 用户交付：空目录采用明确的空List节点或兼容空结果，渲染为空而不抛索引异常。
- 影响模块：contrib/toc_renderer.py:TocRenderer.toc。
- 兼容边界：有标题的List/层级行为保持；空结果类型须公开并兼容调用者。
- 正常验收：空文档/普通段落得到可安全render的空目录。
- 边界／错误验收：仅H1且omit_title、depth过滤全部、自定义条件全部过滤与重复读取幂等。
- 原生回归：test/test_contrib/test_toc_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．目录过滤配置按实例隔离（修复）

- 来源／实际场景：TocRenderer.__init__(filter_conds=[])；实际两个实例共享list。
- 原版现状：向A添加过滤函数后B也具有同一函数。
- 用户交付：缺省每个实例独立集合，传入集合是否复制明确，避免跨文档误隐藏标题。
- 影响模块：contrib/toc_renderer.py:TocRenderer.__init__。
- 兼容边界：显式filter函数调用顺序和异常传播保持；不删除调用者列表的内容。
- 正常验收：更改A过滤条件不影响B，两个文档目录各自正确。
- 边界／错误验收：空/tuple/generator输入兼容、过滤函数报错、重新渲染及默认实例连续创建。
- 原生回归：test/test_contrib/test_toc_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．嵌套解析渲染上下文恢复外层状态（修复）

- 来源／实际场景：[上游#210](https://github.com/miyuchina/mistletoe/issues/210)现状复核；Html→Base→Html同外层复现。
- 原版现状：内层退出reset_tokens导致外层原HTML从可识别变为转义；全局root也未保存嵌套值。
- 用户交付：上下文明确保存/恢复原规则及文档状态，嵌套/异常不破坏外层；并发方案需隔离上下文。
- 影响模块：base_renderer.py进出；block_token.py/span_token.py规则；token.py:_root_node/Document。
- 兼容边界：现有add/remove/reset顶层入口保持；不能只把remove变幂等就称线程安全（现版本已幂等）。
- 正常验收：外层自定义token和原HTML在内层调用前后输出一致。
- 边界／错误验收：异常初始化/解析、同renderer重入、多线程交错与嵌套引用定义不串状态。
- 原生回归：test/test_block_token.py；test/test_span_token.py；test/test_markdown_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．AST children可迭代值和父关系一致（修复）

- 来源／实际场景：token.py:Token.children.setter，生成器和替换孩子真实观察。
- 原版现状：setter消费生成器后children再遍历为空；移除节点parent仍指旧父。
- 用户交付：对允许Iterable一次规范化并维护父子归属，移除时只清理属于该父且不再保留的节点。
- 影响模块：token.py:Token.children/parent；utils.py:traverse相关。
- 兼容边界：既有list的可变性/身份策略须明确；不能无提示允许同节点多个父或形成环。
- 正常验收：用生成器设置后可重复遍历；替换孩子后旧parent清空、新parent正确。
- 边界／错误验收：空/None、复用节点、重复节点、自身/祖先环与自定义迭代器抛错不留下半树。
- 原生回归：test/test_traverse.py；test/test_repr.py；新增Token契约回归。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．Markdown文字回写保持语义（修复）

- 来源／实际场景：[上游#264](https://github.com/miyuchina/mistletoe/issues/264)；&#35; heading真实往返。
- 原版现状：原HTML是段落# heading，回写成# heading后重解析为标题。
- 用户交付：根据段落/行首/行内语境转义还原后的字面文本，避免无意创建Markdown语法。
- 影响模块：markdown_renderer.py:render_raw_text/Fragment/span_to_lines及块布局。
- 兼容边界：保留既有源分隔符/折行选项；目标语义等价，不要求逐字节还原所有空白。
- 正常验收：实体井号往返仍段落，HTML(original)==HTML(rewritten)。
- 边界／错误验收：列表/引用引入符、实体空白、强调/链接边界、折行后新行首和代码文字不被二次转义。
- 原生回归：test/test_markdown_renderer.py；652个原生CommonMark样例做往返补充。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．深层列表采用受控解析预算（修复）

- 来源／实际场景：[上游#279](https://github.com/miyuchina/mistletoe/issues/279)；250层有序列表实际RecursionError。
- 原版现状：List.read/ListItem.read递归耗尽解释器栈，清理语义不确定。
- 用户交付：提供明确深度预算/错误类型或规定回退，超限有界退出并恢复解析状态。
- 影响模块：block_token.py:List/ListItem/Document；block_tokenizer.py；解析预算。
- 兼容边界：普通CommonMark嵌套结果保持；预算超过时明确错误/降级，不默默丢内容。
- 正常验收：正常多层列表输出保持，超过预算得到结构化限额结果而非任意RecursionError。
- 边界／错误验收：有序/无序混合、引用内列表、超限后再次解析、宽大浅树与自定义Token递归范围明确。
- 原生回归：test/test_block_token.py；test/specification完整基线。
- 实际功能依赖：05。

### 09．可选禁止特定原始HTML标签（增强）

- 来源／实际场景：[上游#301](https://github.com/miyuchina/mistletoe/issues/301)；原版process_html_tokens全开/全关对照。
- 原版现状：不能允许em同时只转义script等指定标签。
- 用户交付：增加显式选择性raw HTML规则，命中的标签按约定转义或移除，普通HTML保留。
- 影响模块：html_renderer.py:render_html_span/render_html_block与配置。
- 兼容边界：默认CommonMark原HTML行为保持，原process_html_tokens=False仍全部转义；该规则不冒充全面HTML sanitizer。
- 正常验收：开启指定策略后script标签可见转义而em保留。
- 边界／错误验收：大小写、属性、未闭合标签、整块/行内、注释及标签名称边界不误伤scripture等文字。
- 原生回归：test/test_html_renderer.py；test/specification基线。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．可选链接和图片URL协议策略（增强）

- 来源／实际场景：[上游#269](https://github.com/miyuchina/mistletoe/issues/269)线索；合成javascript目标实际保留。
- 原版现状：escape_url仅quote/HTML转义，没有协议限制；未验证该issue所述CVE。
- 用户交付：增加调用方可选URL允许策略，链接/图片/autolink统一应用并有明确拒绝输出。
- 影响模块：html_renderer.py:escape_url/render_link/render_image/render_auto_link。
- 兼容边界：默认兼容或显式切换profile；保留相对URL/锚点/mailto合法用途，不执行或联网检查URL。
- 正常验收：允许https/相对链接，策略拒绝合成javascript目标，显示文字保留。
- 边界／错误验收：大小写、前导控制/空白、实体解码、data图片子集、坏URL、回调异常处理一致。
- 原生回归：test/test_html_renderer.py；test/test_span_token.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．定义列表语法和渲染（增强）

- 来源／实际场景：[上游#235](https://github.com/miyuchina/mistletoe/issues/235)；Term冒号definition只成段落。
- 原版现状：没有DefinitionList/Term/Definition结构，第二行起始语法无法直接靠单行start断言。
- 用户交付：增加可选定义列表扩展，lookahead读取后决定接受或回退，HTML输出dl/dt/dd。
- 影响模块：block_token.py扩展/独立contrib；block_tokenizer.py回退；各renderer映射。
- 兼容边界：默认CommonMark不启用；普通冒号段落、表格和Setext优先级保持。
- 正常验收：单/多个定义及定义内行内格式输出正确dl结构。
- 边界／错误验收：多段/缩进/嵌套列表、无定义、空term与回退不丢读取行，Markdown回写可解析。
- 原生回归：test/test_block_token.py；test/test_html_renderer.py；test/test_markdown_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．引用式脚注及返回链接（增强）

- 来源／实际场景：[上游#47](https://github.com/miyuchina/mistletoe/issues/47)；Body[^1]原样段落。
- 原版现状：Footnote类只做链接引用定义，[^n]没有脚注结构。
- 用户交付：可选新增脚注定义/引用节点，按首次引用编号，HTML末尾注释及回链。
- 影响模块：独立脚注扩展；Document状态；html/markdown renderer。
- 兼容边界：不重用现Footnote的链接语义；禁用扩展后保持原文，文档作用域隔离。
- 正常验收：多次引用同注释只定义一次，编号顺序与每个回链都正确。
- 边界／错误验收：未定义/未引用、重复标签、嵌套引用、代码内伪脚注、多段定义及独立文档ID冲突明确。
- 原生回归：test/test_block_token.py；test/test_span_token.py；test/test_html_renderer.py。
- 实际功能依赖：05。

### 13．输出Atlassian Document Format（增强）

- 来源／实际场景：[上游#230](https://github.com/miyuchina/mistletoe/issues/230)、[官方ADF结构](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/)；AstRenderer JSON核对。
- 原版现状：AST调试根Document/children，不是ADF根type=doc、version=1、content。
- 用户交付：新增离线ADF renderer，先声明支持段落/标题/列表/代码和基础marks子集，输出可校验JSON。
- 影响模块：新增contrib/adf_renderer.py；BaseRenderer；AST转结构输出。
- 兼容边界：不改AstRenderer调试格式，不调用Jira/Confluence；不支持节点显式失败或按声明降级。
- 正常验收：粗体段落产生ADF text+strong mark，文档保序且满足冻结schema子集。
- 边界／错误验收：空文档、链接/图片策略、HTML、未知自定义Token、嵌套限制与schema不支持项可诊断。
- 原生回归：test/test_ast_renderer.py；新增离线ADF schema/结构回归。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．显式无表头表格扩展（增强）

- 来源／实际场景：[上游#60](https://github.com/miyuchina/mistletoe/issues/60)；分隔行在首部当前仅段落。
- 原版现状：Table构造有无header分支，但read保证第二行delimiter使无header路径不可达。
- 用户交付：增加可选headerless语法，生成无header Table，HTML/Markdown/LaTeX出口有明确表示。
- 影响模块：block_token.py:Table.start/read/__init__；表格renderers。
- 兼容边界：默认GFM表头规则保持，不擅自把普通---段落变表格。
- 正常验收：扩展开启后首行分隔+两行数据输出tbody且不造空表头。
- 边界／错误验收：单列/空表、转义管道、对齐、列数差异和关闭扩展后的回退正确。
- 原生回归：test/test_block_token.py；test/test_html_renderer.py；test/test_markdown_renderer.py；test/test_latex_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．可选智能标点转换（增强）

- 来源／实际场景：[上游#139](https://github.com/miyuchina/mistletoe/issues/139)；引号/双连字符/省略号保持原样。
- 原版现状：无内置typography阶段，用户需自己遍历RawText。
- 用户交付：可选文本变换阶段处理声明的引号/破折号/省略号等，保持跨行内格式的可控边界。
- 影响模块：span_token.py或独立contrib变换；renderer配置。
- 兼容边界：默认原文保持；代码、URL、原HTML属性不转换，不根据未知语言盲改所有撇号。
- 正常验收：启用后普通英文引号/--/...转换，禁用保持原文。
- 边界／错误验收：缩写/数字范围、嵌套引号、链接文字与目标区别、代码片段和多语言引号规则可选择。
- 原生回归：test/test_span_token.py；test/test_html_renderer.py；test/test_markdown_renderer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．块和行内节点提供精确源码区间（增强）

- 来源／实际场景：[上游#144](https://github.com/miyuchina/mistletoe/issues/144)的后续范围；Strong实际没有行列字段。
- 原版现状：已有块line_number，但无结束位置或行内列/偏移，不能精确标记链接错误。
- 用户交付：增加可选source range，明确原始字符偏移及1-based行列，保留变换来源映射。
- 影响模块：block_tokenizer.py、span_tokenizer.py、core_tokens.py；Token/AST导出。
- 兼容边界：保留现块line_number；默认关闭可避免成本，CRLF/制表符/Unicode偏移口径必须定义。
- 正常验收：跨行链接和粗体范围准确，解析原切片可定位到用户文本。
- 边界／错误验收：转义/实体/缩进剥离、引用/list嵌套、tabs、CRLF和自定义token缺映射采用明确未知值。
- 原生回归：test/test_line_numbers.py；test/test_ast_renderer.py；test/test_span_token.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．目录条目跳到稳定标题锚点（增强）

- 来源／实际场景：TocRenderer原生目录实测只有文字，HTML无id/href。
- 原版现状：有层级文字目录，但无法点击定位重复标题。
- 用户交付：增加显式锚点策略，标题id与目录href共用一次分配，支持重复标题后缀。
- 影响模块：contrib/toc_renderer.py:TocRenderer；HtmlRenderer标题协作。
- 兼容边界：默认原HTML/纯文字TOC可保留；不重解析渲染HTML作为标题身份，避免实体/标记歧义。
- 正常验收：两个Same标题获得不同稳定id，目录链接均对应真实标题。
- 边界／错误验收：中文/空标题、标点、已有自定义id、过滤/深度/跳级、同实例多文档状态清理。
- 原生回归：test/test_contrib/test_toc_renderer.py；test/test_html_renderer.py。
- 实际功能依赖：01, 03, 04。

### 18．非交互stdin作为单份文档转换（增强）

- 来源／实际场景：CLI无filename只进interactive；受控input证明每次EOF回REPL。
- 原版现状：管道输入没有一次消费后退出模式；0.1秒真实子进程观察只作补充，已回收。
- 用户交付：增加stdin文件标识-或非TTY批处理模式，EOF渲染一次并正常退出。
- 影响模块：cli.py:main/convert_file/interactive；__main__.py。
- 兼容边界：显式交互REPL保留Ctrl-D完成当前块的行为；不能因新增pipe模式破坏真人REPL。
- 正常验收：pipe Markdown转一次HTML并退出0，stdout无banner/prompt，可与文件输出组合。
- 边界／错误验收：空stdin、无尾换行、UTF-8错误、-与多文件组合、broken pipe和KeyboardInterrupt正确收尾。
- 原生回归：test/test_cli.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．CLI渲染器协议错误可理解（修复）

- 来源／实际场景：[上游#302](https://github.com/miyuchina/mistletoe/issues/302)；真实CLI选择Scheme得到KeyError Document。
- 原版现状：_import只检查模块属性存在，不兼容Document/str输出的对象直接内部堆栈。
- 用户交付：在CLI转换前声明/校验所需renderer协议，不兼容出口给清楚错误及非零退出。
- 影响模块：cli.py:_import/convert_file；BaseRenderer支持根类型边界。
- 兼容边界：可信自定义模块仍可使用；Scheme解释器继续用Program原生入口，不为修错误自动执行代码。
- 正常验收：合法HTML/Markdown/LaTeX/Ast正常；Scheme或普通函数作为renderer有可读错误无内部KeyError。
- 边界／错误验收：对象非类、构造失败、缺context/render、返回非str和真实renderer内部错误不能一概误报导入失败。
- 原生回归：test/test_cli.py；test/test_contrib/test_scheme.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．LaTeX字面文字正确转义反斜线和波浪（修复）

- 来源／实际场景：latex_renderer.py:render_raw_text；合成\alpha ~输出仍为TeX语法。
- 原版现状：普通Markdown文本的反斜线与~直接进入LaTeX，与字面文本语义不符。
- 用户交付：补齐文本模式特殊字符转义，保留原生数学和代码的明确不转义路径。
- 影响模块：latex_renderer.py:render_raw_text；latex_token.py边界。
- 兼容边界：不对数学命令/verb/listing内容重复转义；本轮只证明输出字符串，未声称TeX引擎编译结果。
- 正常验收：普通\alpha显示为字面反斜线+alpha、~为字面波浪，已有特殊符号保持。
- 边界／错误验收：混合$/{/}/\文本、反斜线转义顺序、代码/数学/URL/图片文件名使用各自正确上下文。
- 原生回归：test/test_latex_renderer.py；test/test_latex_token.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

已支持块起始line_number、Token.parent、带深度/类过滤的traverse、表格和删除线、HTML全部禁用转义、AST/HTML/LaTeX/Markdown/Jira/XWiki等出口、引用链接定义回写、TOC文字列表、Pygments着色和Markdown折行。#144的块行号已存在，不重复计步；#210旧remove_token ValueError在该commit已做幂等保护，不照抄为当前BUG。Footnote类实际是链接引用定义，不等于[^n]引用脚注；补尾换行是renderer既有行为，不当作缺陷凑步。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
