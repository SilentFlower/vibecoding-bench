# Python-Markdown：二十步真实工程路线

固定 [Python-Markdown/markdown@b41e0aaf1181f1a8cb200cf5a815aad7c0020d23](https://github.com/Python-Markdown/markdown/tree/b41e0aaf1181f1a8cb200cf5a815aad7c0020d23)。原生基线 1019 通过、110 跳过；范围和限制见 [单仓审查](./python-markdown.md)。类型计数：{"修复": 4, "增强": 16}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．折叠引用标签中的代码片段（修复）

- 来源／实际场景：[上游 #495](https://github.com/Python-Markdown/markdown/issues/495)，固定原版重放。
- 原版现状：包含`code`的折叠引用保留为字面，而对应引用定义已存在。
- 用户交付：在行内占位符处理后仍正确查找原引用标签并生成链接。
- 影响模块：inlinepatterns.py:ReferenceInlineProcessor与treeprocessors.py行内阶段。
- 兼容边界：保持大小写归一和普通显式引用；不把反引号从显示文本删掉。
- 正常验收：含强调/代码的折叠引用href正确，标签含code元素。
- 边界／错误验收：未定义、转义反引号、嵌套括号不错误匹配，代码中的链接不展开。
- 原生回归：tests/test_legacy.py、tests/test_syntax/inline/test_links.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．嵌套 admonition 内原始 HTML 块（修复）

- 来源／实际场景：[上游 #1096](https://github.com/Python-Markdown/markdown/issues/1096)实际原文。
- 原版现状：有空行的div被拆成<p><div>和</div></p>。
- 用户交付：在缩进容器内部正确识别/恢复完整raw HTML块，保持容器外结构。
- 影响模块：extensions/admonition.py、htmlparser.py、preprocessors.py、postprocessors.py。
- 兼容边界：保留原始HTML允许规则，md_in_html显式解析语义不变；不是新增清洗器。
- 正常验收：含空行div在note内形成完整块，不被p包裹。
- 边界／错误验收：嵌套容器、注释、尾随Markdown、未闭合HTML遵守既有规范。
- 原生回归：tests/test_syntax/extensions/test_admonition.py、test_md_in_html.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．CLI 拒绝静默丢弃的额外文件参数（修复）

- 来源／实际场景：__main__.py:parse_options实际传first.md second.md。
- 原版现状：opts只保留first.md，第二个文件无提示消失。
- 用户交付：单文件模式遇多个位置参数明确错误，不产生貌似完整的部分结果。
- 影响模块：__main__.py:parse_options；tests/test_apis.py。
- 兼容边界：现有零/一位置参数保持；未来批处理必须显式另设计而不靠忽略。
- 正常验收：一文件和stdin照常转换，多文件退出非0说明范围。
- 边界／错误验收：带空格路径视为一个参数；--之后选项样路径可用；错误时不创建输出。
- 原生回归：tests/test_apis.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．Extension 类级配置实例隔离（修复）

- 来源／实际场景：extensions/__init__.py:Extension.config与官方类级定义模式。
- 原版现状：设置首实例label=first，后续无参数实例仍得到first。
- 用户交付：初始化时复制每实例配置容器，修改某实例不污染默认或其他实例。
- 影响模块：extensions/__init__.py:Extension.__init__/setConfig。
- 兼容边界：保留继承、实例内self.config与回调对象身份；不要对不可复制callable盲目deepcopy。
- 正常验收：两个实例和继承子类的配置独立，默认描述不变。
- 边界／错误验收：嵌套可变配置明确复制策略；bool/None转换和未知键错误保持。
- 原生回归：tests/test_extensions.py:TestExtensionClass。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．可选更广 URI 自动链接策略（增强）

- 来源／实际场景：[上游 #1244](https://github.com/Python-Markdown/markdown/issues/1244)；ssh/urn使用场景。
- 原版现状：<ssh://example.com>和<urn:example:one>作为raw HTML字面输出。
- 用户交付：增加opt-in URI autolink扩展，按可配置scheme解析而非误当标签。
- 影响模块：inlinepatterns.py、htmlparser.py；新增扩展入口。
- 兼容边界：默认Gruber风格行为保持；不是无条件允许危险协议。
- 正常验收：开启后ssh/urn按所选策略形成完整a元素。
- 边界／错误验收：普通em标签、邮箱、冒号文本、恶意scheme不误转；URL属性安全转义。
- 原生回归：tests/test_syntax/inline、tests/test_legacy.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．目录可忽略指定标题（增强）

- 来源／实际场景：[上游 #1178](https://github.com/Python-Markdown/markdown/issues/1178)；data-toc-unlisted原版重放。
- 原版现状：标记仍输出到HTML并进入toc_tokens。
- 用户交付：TOC可识别显式unlisted属性，只排除目录项并保留正常标题/id。
- 影响模块：extensions/toc.py、extensions/attr_list.py。
- 兼容边界：标题层级/anchor/permalink保持；属性是否移除明确配置。
- 正常验收：两个标题之一标为unlisted时目录仅列公开项。
- 边界／错误验收：嵌套标题/缺属性值/自定义label/多个TOC标记一致，不误隐藏子节正文。
- 原生回归：tests/test_syntax/extensions/test_toc.py、test_attr_list.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．表格 caption 与可访问说明（增强）

- 来源／实际场景：tables.TableExtension只有use_align_attribute配置；原生表格后说明场景。
- 原版现状：`: 表格说明`变成普通段落，没有caption关联。
- 用户交付：opt-in识别紧邻表格的caption语法并输出caption，供读屏和导出使用。
- 影响模块：extensions/tables.py:TableProcessor/TableExtension。
- 兼容边界：默认语法保持；普通冒号段落不得跨空白远距离吸附。
- 正常验收：启用后表头/内容/caption在同一table内，中文和行内格式正确。
- 边界／错误验收：无表格、多个表格、空caption、原始HTML和代码中的伪caption不误匹配。
- 原生回归：tests/test_syntax/extensions/test_tables.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．容器内围栏代码块（增强）

- 来源／实际场景：官方fenced_code扩展的原生引用块场景。
- 原版现状：引用内围栏被当code span，丢独立代码块与语言。
- 用户交付：提供opt-in块处理扩展/模式，支持引用和列表内围栏代码。
- 影响模块：extensions/fenced_code.py、blockprocessors.py。
- 兼容边界：保持默认历史语法；新增实现不能靠删除引用/列表前缀破坏兄弟内容。
- 正常验收：列表/引用内代码生成pre/code并保留语言及缩进。
- 边界／错误验收：多层嵌套、空行、未闭合围栏、属性与高亮组合无越界吞文。
- 原生回归：tests/test_syntax/extensions/test_fenced_code.py、test_legacy.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．围栏结束长度兼容模式（增强）

- 来源／实际场景：原版三反引号开、四反引号关的实际技术文档。
- 原版现状：要求关闭长度完全相等，示例被当代码span且语言首字丢失。
- 用户交付：opt-in采用同字符且长度不小于开头的关闭策略，便于粘贴常见文档。
- 影响模块：extensions/fenced_code.py:FENCED_BLOCK_RE/run。
- 兼容边界：默认不强行宣称CommonMark；仅新模式接受更长关闭，保留内部短围栏。
- 正常验收：三开四关内容完整，反引号/波浪符分别工作。
- 边界／错误验收：更短关闭不终止、混用字符不匹配、代码内长围栏与未闭合规则确定。
- 原生回归：tests/test_syntax/extensions/test_fenced_code.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．高亮后保留代码块锚点（增强）

- 来源／实际场景：fenced_code.py明确忽略id；代码注释链接到示例。
- 原版现状：{.python #sample}在CodeHilite开启时sample完全消失。
- 用户交付：可选把围栏id应用于高亮外层容器，允许稳定链接到示例。
- 影响模块：extensions/fenced_code.py、extensions/codehilite.py。
- 兼容边界：不把id直接拼到Pygments未转义输出；非高亮id位置保持。
- 正常验收：高亮开/关都存在且仅存在一个sample目标。
- 边界／错误验收：恶意id、重复id、自定义formatter与noclasses组合不破坏HTML。
- 原生回归：tests/test_syntax/extensions/test_fenced_code.py、test_code_hilite.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．Wiki 链接支持别名与片段（增强）

- 来源／实际场景：wikilinks.WIKILINK_RE只匹配字词/空格；知识库[[Page|alias]]路径。
- 原版现状：别名和#fragment两例均保持字面。
- 用户交付：扩展可选支持独立目标、显示名和页内片段，复用build_url。
- 影响模块：extensions/wikilinks.py:WikiLinksInlineProcessor。
- 兼容边界：原[[Page]]、Meta提供的base/end/class和自定义build_url保持。
- 正常验收：目标含空格而显示中文别名时URL/label分离，片段指向正确页。
- 边界／错误验收：空目标、转义管道、多个#、嵌套普通链接、原始HTML不误消费。
- 原生回归：tests/test_extensions.py、tests/test_legacy.py:WikiLinks。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．显式结构化元数据解析（增强）

- 来源／实际场景：meta.MetaPreprocessor及嵌套settings/tags真实文档。
- 原版现状：所有值是list[str]，嵌套depth被摊平，tags只是字面字符串。
- 用户交付：meta可选parser接收头块，结构化模式使用安全YAML或调用者parser并返回映射。
- 影响模块：extensions/meta.py:MetaExtension/MetaPreprocessor。
- 兼容边界：默认旧扁平Meta继续；结构化模式不自动实例化任意Python对象。
- 正常验收：嵌套映射、列表、布尔按选定解析器得到数据，正文保留。
- 边界／错误验收：坏YAML、重复键策略、无结束标记和超大头块明确失败，无半份Meta。
- 原生回归：tests/test_meta.py、tests/test_extensions.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 13．公开结构化转换结果（增强）

- 来源／实际场景：core.convert只有str返回；调用者需同时得到HTML/元数据/TOC/树。
- 原版现状：无公开parse或convert_result，通常自写treeprocessor捕获内部root。
- 用户交付：提供convert_result返回HTML、可读取树副本、元数据/TOC与诊断，并定义一次转换边界。
- 影响模块：core.py:Markdown.convert；treeprocessors.py；扩展结果协议。
- 兼容边界：convert原返回不变；树阶段和raw HTML占位符是否恢复须明确，不自称标准CommonMark AST。
- 正常验收：同次结果HTML与convert等价，TOC/Meta属于本次文档。
- 边界／错误验收：后续reset/转换不改写旧结果；异常不返回伪完整对象；缺扩展字段明确为空。
- 原生回归：tests/test_apis.py、tests/test_meta.py、test_toc.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．分别指定输入和输出编码（增强）

- 来源／实际场景：convertFile只有encoding单参；遗留GBK文档输出UTF-8场景。
- 原版现状：读写同一encoding，调用者需另包流转换。
- 用户交付：增加input_encoding/output_encoding可选参数，默认回退原encoding。
- 影响模块：core.py:convertFile/markdownFromFile；__main__.py。
- 兼容边界：旧encoding同时控制两端保持；XML字符引用替代策略可显式选择。
- 正常验收：GBK输入写出UTF-8中文HTML，CLI对应参数一致。
- 边界／错误验收：未知编码、坏字节、不可表示字符、stdin/stdout组合行为清楚，错误不伪成功。
- 原生回归：tests/test_apis.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．文件 API 接受 PathLike（增强）

- 来源／实际场景：原生PosixPath作为input复现AttributeError；现代pathlib调用场景。
- 原版现状：仅str被当路径，Path对象落入codec reader尝试.read。
- 用户交付：使用os.fspath识别受支持PathLike输入/输出，流对象继续原协议。
- 影响模块：core.py:convertFile；公开类型定义。
- 兼容边界：不把任何有__str__的对象视为路径；保持BinaryIO能力。
- 正常验收：Path、PurePath可读写，字符串路径输出一致。
- 边界／错误验收：bytes路径支持策略明确；错误PathLike返回值/目录/缺文件清楚报告。
- 原生回归：tests/test_apis.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．CLI 声明式安全配置模式（增强）

- 来源／实际场景：__main__.py明确使用PyYAML unsafe_load；受控构建配置场景。
- 原版现状：CLI配置默认允许Python对象，无safe-config选项。
- 用户交付：增加显式safe-config模式，限制JSON/安全YAML的映射/标量/序列，适合CI收取配置。
- 影响模块：__main__.py:yaml_load/parse_options。
- 兼容边界：可信现有配置通过显式legacy模式保留；不把原可信CLI声明为远程漏洞。
- 正常验收：普通toc_depth/bool配置正常，YAML与JSON等价。
- 边界／错误验收：Python对象tag、非映射根、超深/别名膨胀和错误配置拒绝且不执行导入构造。
- 原生回归：tests/test_apis.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．引用错误的结构化诊断（增强）

- 来源／实际场景：构建文档需要知道missing及重复引用；原版references只留有效项。
- 原版现状：缺失保留字面，重复定义被覆盖/忽略，无规范化诊断字段。
- 用户交付：可选收集显式未定义引用、重复定义来源及未匹配语法类别，strict由调用方决定。
- 影响模块：blockprocessors.py:ReferenceProcessor；inlinepatterns.py；结果对象。
- 兼容边界：普通宽松HTML保持；不把任意方括号或合法raw HTML判错。
- 正常验收：前向定义成功无诊断，missing与duplicate分别定位。
- 边界／错误验收：代码/转义/脚注/重复大小写归一不误报，日志不打印整篇正文。
- 原生回归：tests/test_syntax/inline、tests/test_legacy.py。
- 实际功能依赖：13。

### 18．可选严格构造参数校验（增强）

- 来源／实际场景：Markdown(tba_length=9)与unknown_option实测被静默忽略。
- 原版现状：拼错参数保持默认tab_length=4而不提醒。
- 用户交付：strict_options模式拒绝未知kwargs并验证tab_length等公开参数类型/范围。
- 影响模块：core.py:Markdown.__init__；__main__.py。
- 兼容边界：默认宽松兼容现有扩展kwargs；允许扩展声明自己的配置键而非一刀切。
- 正常验收：合法构造/扩展声明通过，拼写错误提示未知键和建议。
- 边界／错误验收：bool冒充整数、零/负tab长度、非映射extension_configs明确拒绝且不部分注册。
- 原生回归：tests/test_apis.py、tests/test_extensions.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．CLI 查看可用扩展与配置说明（增强）

- 来源／实际场景：Extension.getConfigInfo和entry point元数据已有，但CLI只接受-x。
- 原版现状：没有list-extensions/describe-extension入口，用户需写Python查找。
- 用户交付：提供扩展发现和配置说明命令，输出来源、名称和可序列化默认值。
- 影响模块：__main__.py；util.py:get_installed_extensions；extensions/__init__.py。
- 兼容边界：仅显式查看时加载所选扩展；列表不执行未知插件任意代码，不泄露不可序列化对象内部内容。
- 正常验收：内置扩展名和toc配置说明可读/JSON均稳定。
- 边界／错误验收：同名entry point冲突、缺依赖、插件初始化失败有可读诊断，普通转换stdout不混入列表。
- 原生回归：tests/test_apis.py、tests/test_extensions.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．输入流所有权可显式保留（增强）

- 来源／实际场景：convertFile的BinaryIO读写真实场景；BytesIO输入被close但输出保留。
- 原版现状：传入的caller输入流被无条件关闭，调用者无法复用。
- 用户交付：增加明确close_input/流所有权策略，允许保留调用者流并确保自开的路径句柄异常也关闭。
- 影响模块：core.py:Markdown.convertFile。
- 兼容边界：旧默认关闭策略若保留须明示；新keep-open模式不关闭caller流，输出既有不关闭保持。
- 正常验收：keep-open后可seek/read源流，路径输入打开的句柄正常收口。
- 边界／错误验收：解码失败、read失败、转换异常和输出失败仍按所有权清理，不能误关stdin。
- 原生回归：tests/test_apis.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

保留既有HTML/XHTML、裸布尔属性、meta扁平文本、TOC层级/Unicode自定义slug、脚注多引用回链及UNIQUE_IDS/USE_DEFINITION_ORDER、fenced_code属性和高亮、Registry扩展机制作为回归。Python-Markdown明确不清洗不可信HTML，本路线不把它包装成HTML sanitizer，也不将与CommonMark的所有差异认定BUG。第三方pymdown-extensions可解决部分功能，但本仓尚未提供这些原生可选能力，路线应说明采用内置实现与外部扩展的取舍。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
