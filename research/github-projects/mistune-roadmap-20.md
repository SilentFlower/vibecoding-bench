# Mistune：二十步真实工程路线

固定 [lepture/mistune@4bbaa04c391d650a2e1219781c9a9acd60571cce](https://github.com/lepture/mistune/tree/4bbaa04c391d650a2e1219781c9a9acd60571cce)。原生基线 1324 主测试通过、158 子测试通过、0 跳过；范围和限制见 [单仓审查](./mistune.md)。类型计数：{"修复": 2, "增强": 18}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．空输入作为合法空文档（修复）

- 来源／实际场景：原生 CLI stdin 与 -m 空串场景；__main__.py:cli 的真值判断。
- 原版现状：空 stdin 返回1并输出缺少消息，Python API对空文本可正常解析。
- 用户交付：区分未提供输入与已提供的零字节文档，管道空文档成功产生空结果。
- 影响模块：__main__.py:cli/read_stdin；tests/test_cli.py。
- 兼容边界：交互终端无参数仍提示用法；非空文本和文件优先级保持。
- 正常验收：空 stdin、显式 -m 空串和零字节文件退出0且输出不含错误提示。
- 边界／错误验收：缺文件非0；不能因读取交互 stdin 永久阻塞；字符串0不误判。
- 原生回归：tests/test_cli.py、tests/test_misc.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．CLI 导出结构化 AST JSON（增强）

- 来源／实际场景：CLI --renderer 与现有 create_markdown(renderer="ast") 的实际组合。
- 原版现状：-r ast -m 标题解析成list后触发 assert isinstance(text,str)。
- 用户交付：CLI ast 渲染结果按 UTF-8 JSON 输出到stdout或-o文件，供编辑器与索引器使用。
- 影响模块：__main__.py:_md/_output/cli。
- 兼容边界：HTML、Markdown和RST文本输出保持；未知renderer明确拒绝而非猜测。
- 正常验收：CLI JSON可解析，token类型/中文/嵌套与API AST等价。
- 边界／错误验收：空文档输出合法空数组；写失败退出非0且无混合日志污染JSON。
- 原生回归：tests/test_cli.py、tests/test_syntax.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．同一脚注多次引用生成唯一锚点与回链（修复）

- 来源／实际场景：plugins/footnotes.py:render_footnote_ref；实际A[^x] B[^x]。
- 原版现状：两个引用均输出id=fnref-1，脚注只回到同一id。
- 用户交付：每个引用实例唯一id，脚注提供指向全部引用的回链。
- 影响模块：plugins/footnotes.py；tests/test_plugins.py、test_security_footnotes.py。
- 兼容边界：单次引用原样式/编号保持；脚注展示顺序仍按首次引用。
- 正常验收：两次和三次引用全部id唯一、href有目标，回链可逐个返回。
- 边界／错误验收：未定义脚注仍字面；不同注释、代码里的伪引用不重复编号；转义保持。
- 原生回归：tests/test_plugins.py、tests/test_security_footnotes.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．可选 token 源位置映射（增强）

- 来源／实际场景：[上游 #402](https://github.com/lepture/mistune/issues/402)；编辑器定位原始列表。
- 原版现状：块与行内token没有start/end或position，嵌套内容重写后难映回原文。
- 用户交付：opt-in source_positions记录原始字符偏移及行列，嵌套列表和引用保留映射。
- 影响模块：core.py:BlockState/InlineState；block_parser.py、list_parser.py、inline_parser.py。
- 兼容边界：默认token结构和性能路径保持；明确偏移基于Unicode码点，不声称字节偏移。
- 正常验收：按位置切片可取回标题、列表、链接原始片段。
- 边界／错误验收：CRLF、制表符、非BMP字符、引用前缀与空节点位置有定义，不能按规范化文本偷算。
- 原生回归：tests/test_syntax.py、test_commonmark.py、test_inline_limits.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．HTML 自定义方法读取本次上下文（增强）

- 来源／实际场景：[上游 #391](https://github.com/lepture/mistune/issues/391)；不同文档图片前缀。
- 原版现状：render_token收到state，但调用image/link等传统方法只传text及attrs。
- 用户交付：新增opt-in上下文分派协议，让自定义渲染方法可读取state.env且不改共享renderer字段。
- 影响模块：renderers/html.py:HTMLRenderer.render_token；core.py:BaseRenderer。
- 兼容边界：旧签名继续工作；上下文不可在跨文档缓存中残留。
- 正常验收：同一个renderer连续解析两个state，得到各自prefix。
- 边界／错误验收：嵌套渲染和回调异常不污染后续文档；不假称任意插件自动线程安全。
- 原生回归：tests/test_renderers.py、tests/test_hooks.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．原生纯文本 renderer（增强）

- 来源／实际场景：搜索索引与终端摘要需要去结构但保留可读文本；renderers目录和入口已核对。
- 原版现状：只有HTML、Markdown、RST等renderer，去HTML标签会丢列表/图片语义。
- 用户交付：提供PlainTextRenderer，定义段落、列表、代码、图片alt和链接文本的可读输出。
- 影响模块：renderers/新增纯文本模块；__init__.py、__main__.py。
- 兼容边界：默认仍HTML；不把纯文本当HTML安全清洗工具。
- 正常验收：标题/嵌套列表/代码/链接导出无标签且结构可读。
- 边界／错误验收：空alt、硬换行、转义实体、未知插件给明确信息，不默默丢正文。
- 原生回归：tests/test_renderers.py、tests/test_plugins.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．Markdown renderer 保留脚注（增强）

- 来源／实际场景：将带footnotes插件的文档重新格式化；实际调用MarkdownRenderer。
- 原版现状：遇到footnote_ref缺少方法抛AttributeError。
- 用户交付：生成稳定脚注引用与定义，格式化后重新解析语义不丢失。
- 影响模块：renderers/markdown.py；plugins/footnotes.py。
- 兼容边界：HTML脚注输出保持；不承诺原始空白字节完全保留。
- 正常验收：多段脚注、多个引用的Markdown往返保留正文和编号关系。
- 边界／错误验收：脚注含代码、列表、引用定义和重复标识采用已定义胜出规则。
- 原生回归：tests/test_renderers.py、tests/test_plugins.py；依赖03回链回归。
- 实际功能依赖：03。

### 08．RST renderer 导出 Markdown 表格（增强）

- 来源／实际场景：文档工具使用现有-r rst及table插件；实际API调用。
- 原版现状：RSTRenderer未实现table，输出时AttributeError。
- 用户交付：将表格输出为可解析的RST list-table，保留表头与多行单元格。
- 影响模块：renderers/rst.py；plugins/table.py。
- 兼容边界：HTML/Markdown表格不变；不引入RST解析服务作为运行依赖。
- 正常验收：中文、对齐、转义竖线的表格生成有效list-table。
- 边界／错误验收：空body、代码span、长单元格和嵌套标记无数据丢失；不声称列宽字节对齐。
- 原生回归：tests/test_renderers.py、tests/test_plugins.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．AST 模式提供目录元数据（增强）

- 来源／实际场景：编辑器同时需要AST与目录；toc.add_toc_hook实际调用。
- 原版现状：renderer=None时normalize_toc_item断言失败，无法直接配AST。
- 用户交付：目录提取可独立于HTMLrenderer，输出标题纯文本、level、id到state。
- 影响模块：toc.py:add_toc_hook/normalize_toc_item。
- 兼容边界：HTML目录既有转义和render_toc_ul保持；不强制把HTMLrenderer塞进AST结果。
- 正常验收：AST和HTML模式对同一标题得到一致的目录文本/id。
- 边界／错误验收：标题含强调、code、实体、图片和空内容时有确定文本策略。
- 原生回归：tests/test_hooks.py、tests/test_security_toc.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．可选收录嵌套容器标题（增强）

- 来源／实际场景：复杂文档引用/列表内的标题需要导航；toc_hook实际只遍历state.tokens。
- 原版现状：顶层标题有toc item，引用内标题不入目录。
- 用户交付：为TOC增加显式包含容器配置，深度优先按阅读顺序收录。
- 影响模块：toc.py:toc_hook；directives/toc.py。
- 兼容边界：默认只收顶层保持；排除代码与未解析raw HTML伪标题。
- 正常验收：嵌套引用和列表标题按阅读顺序出现在目录。
- 边界／错误验收：标题级别过滤、重复id、include来源组合不重复收录。
- 原生回归：tests/test_hooks.py、tests/test_directives.py；可组合09。
- 实际功能依赖：09。

### 11．内置可读且唯一的标题 slug 策略（增强）

- 来源／实际场景：静态文档希望标题变成稳定语义链接；原版heading_id可自定义但默认toc_序号。
- 原版现状：中文同名标题分别toc_1/toc_2，没有可选标准slug策略。
- 用户交付：提供可选Unicode slug分配器，去装饰、稳定重复后缀并避开已有HTML id。
- 影响模块：toc.py:_HeadingIdAllocator；directives/toc.py。
- 兼容边界：保留默认toc_N和自定义callback语义，不无条件改变旧链接。
- 正常验收：相同标题文本在不相关段落插入后slug不变，重复标题后缀唯一。
- 边界／错误验收：空标题、全标点、实体、大小写及既有id冲突有确定规则且属性转义。
- 原生回归：tests/test_hooks.py、tests/test_security_toc.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．脚注文档命名空间（增强）

- 来源／实际场景：两个独立Markdown片段合成同页；实际合并原生输出。
- 原版现状：两段均生成fn-1/fnref-1导致跨文档id冲突。
- 用户交付：footnotes可设置本次文档prefix，同时应用引用目标和回链。
- 影响模块：plugins/footnotes.py；Markdown state.env配置入口。
- 兼容边界：默认前缀保持；命名空间与同文档多次引用计数解决不同问题。
- 正常验收：两份文档不同prefix合并后所有id唯一且href正确。
- 边界／错误验收：prefix含引号、空格或非法值拒绝/安全编码；复用实例不串prefix。
- 原生回归：tests/test_plugins.py、test_security_footnotes.py。
- 实际功能依赖：03。

### 13．引用诊断报告（增强）

- 来源／实际场景：文档构建检查未定义引用与重复定义；实际missing与重复[x]输入。
- 原版现状：缺引用保留字面，重复定义仅留首项，state无结构化诊断列表。
- 用户交付：opt-in收集缺失/重复引用的类型、标识和位置，不把所有方括号文本判错。
- 影响模块：block_parser.py:parse_ref_link；inline_parser.py；core.py:BlockState。
- 兼容边界：默认宽松输出保持；构建者另选strict模式失败，不改变普通Markdown规则。
- 正常验收：合法前向引用不报警，确实无法解析的显式引用有诊断。
- 边界／错误验收：转义、代码span、图片、include重复定义的来源准确且不泄露全文。
- 原生回归：tests/test_commonmark.py、tests/test_security_ref_links.py。
- 实际功能依赖：04。

### 14．可选 front matter 提取（增强）

- 来源／实际场景：静态文档开头的---元数据与正文分离；已核对内置plugin表。
- 原版现状：无frontmatter插件，示例被解析成thematic_break/heading。
- 用户交付：增加仅文档开头生效的frontmatter插件，原文保存在state.env，可选解析器由调用者提供。
- 影响模块：plugins/新增元数据模块；__init__.py插件注册。
- 兼容边界：默认不开启，不强加PyYAML运行依赖；不把任意Python对象构造作为元数据解析。
- 正常验收：带title/date的头块从正文剥离并可读env，普通正文保留。
- 边界／错误验收：未闭合分隔、BOM、空元数据、正文里的---和大小上限明确。
- 原生回归：tests/test_plugins.py、tests/test_syntax.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．围栏代码属性与标注（增强）

- 来源／实际场景：技术文档希望代码块id/class/行号；原生info字符串观察。
- 原版现状：除第一个语言名外，{#sample .wide linenos=1}被忽略。
- 用户交付：opt-in解析围栏属性，输出受控id/class/data行号信息和AST attrs。
- 影响模块：block_parser.py:parse_fenced_code；renderers/html.py:block_code。
- 兼容边界：默认info原样AST和language类保持；只接受白名单属性，不提供任意on事件。
- 正常验收：代码语言、id、class、行号配置在HTML和AST一致。
- 边界／错误验收：引号/转义、非法属性、重复id、无语言和恶意文本不破坏HTML。
- 原生回归：tests/test_renderers.py、tests/test_security_edge_cases.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．include 指令选择行范围（增强）

- 来源／实际场景：include代码片段的start-line/end-line；原生指定选项实测。
- 原版现状：除了encoding，其他选项未用于读取，三行全部输出。
- 用户交付：支持零起点半开行范围，并可选择字面代码模式，不读无关内容到输出。
- 影响模块：directives/include.py:Include.parse/render_html_include。
- 兼容边界：无范围时现有完整include保持；保留realpath边界/循环保护。
- 正常验收：三行文件选择[1,2)仅含第二行，行号与换行保留。
- 边界／错误验收：负数、逆序、非整数拒绝；越界规则明确；UTF-8和CRLF不混乱。
- 原生回归：tests/test_directives.py、tests/test_security_include.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．include 依赖清单（增强）

- 来源／实际场景：静态文档增量构建需要知道正文依赖文件；检查state.env实际键。
- 原版现状：include完成后没有规范化文件依赖清单。
- 用户交付：可选在state记录实际读取的文件、来源关系和摘要，供调用者做失效判断。
- 影响模块：directives/include.py；core.py:BlockState.env。
- 兼容边界：不启动watcher、不访问网络；默认不公开绝对路径到HTML。
- 正常验收：A含B且B含C时记录唯一依赖和父子关系，修改B可识别变化。
- 边界／错误验收：重复include、失败路径、循环拒绝和权限错误不记录虚假成功依赖。
- 原生回归：tests/test_directives.py、tests/test_security_include.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．可信配置与内置插件策略可分离（增强）

- 来源／实际场景：公开 #461 提醒调用者可能误将不可信参数当配置；实际import_plugin接口。
- 原版现状：字符串既支持内置短名也支持任意dotted插件路径，未提供builtins-only开关。
- 用户交付：增加opt-in builtin_only策略并列出允许插件，适合服务端接受有限用户选项。
- 影响模块：plugins/__init__.py:import_plugin；create_markdown；CLI。
- 兼容边界：默认可信Python扩展和callable插件仍可用；不宣称内置模式构成Python沙箱。
- 正常验收：builtin_only接受table/footnotes，拒绝未知dotted名字且不导入模块。
- 边界／错误验收：callable传入、cached plugin、重复名字和非法配置策略明确，不复用绕过缓存。
- 原生回归：tests/test_plugins.py、tests/test_cli.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．CLI 多文件批量转换（增强）

- 来源／实际场景：文档目录有多份.md需要转换；原版help与参数定义实查。
- 原版现状：只有一个--file和一个--output，无输出目录或文件集合入口。
- 用户交付：显式多文件输入和output-dir保留相对文件名，每文件使用独立state并汇总结果。
- 影响模块：__main__.py:cli/_md/_output。
- 兼容边界：单文件调用保持；不隐式扫描祖先或覆盖未选文件。
- 正常验收：两份不同引用文档分别生成正确HTML，文件名含中文/空格可用。
- 边界／错误验收：输出名冲突、输入缺失、输出等于输入、部分失败退出码和覆盖策略明确。
- 原生回归：tests/test_cli.py、tests/test_security_ref_links.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．链接与图片 URL 重写回调（增强）

- 来源／实际场景：文档搬迁到子路径/CDN，现有HTMLRenderer只提供协议策略和可子类化方法。
- 原版现状：renderer构造无url_resolver；../files/a.pdf原样输出。
- 用户交付：提供opt-in resolver(url,kind,state)统一处理链接和图片，经重写后再做协议检查与属性转义。
- 影响模块：renderers/html.py:link/image/sanitize_url；上下文分派。
- 兼容边界：默认链接保持；URL安全过滤不能被回调绕过；不自动访问链接。
- 正常验收：相对资源按文档base重写，绝对HTTPS保持，图片和普通链接可区别。
- 边界／错误验收：回调抛错/返回错误类型、javascript结果、片段和data图片白名单正确处理。
- 原生回归：tests/test_renderers.py、tests/test_security_urls.py。
- 实际功能依赖：05。

## 累计验收与不计步内容

已存在的安全 URL 策略、默认 HTML 转义、脚注、任务列表、数学、表格及列表／引用中的显式插件、include 路径／循环保护、可自定义 heading_id、可子类化 renderer 都作为回归，不计新增。旧 issue 的标题换行或未知 HTML 标签行为没有直接当作缺陷；CommonMark 允许的规范化不要求字节保真。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
