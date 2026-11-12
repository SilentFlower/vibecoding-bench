# Tabulate：二十步真实工程迭代路线

固定 [astanin/python-tabulate@268615a5c27dc40e5c22454c07b44d5c50410da0](https://github.com/astanin/python-tabulate/tree/268615a5c27dc40e5c22454c07b44d5c50410da0)，详见[单仓审查](./tabulate.md)。共 20 步：15 项增强提案、5 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．分隔行不消耗用户行索引（问题修复）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/464
- 原版现状：_prepend_row_index 在移除 SEPARATING_LINE 前校验长度，2个数据行+1分隔行配2个list索引报错，而iterator成功；已复现。
- 交付目标：按数据行校验与消费显式索引，DataFrame原标签保持绑定真实行。
- 影响模块：tabulate/__init__.py:_prepend_row_index/_normalize_tabular_data
- 兼容边界：分隔行仍作为展示结构，不计数据；显式索引与DataFrame索引要分别保持来源。
- 正常验收：showindex列表/tuple/iterator对a,b分配10,20，分隔线仍在中间。
- 异常／边界：过短／过长索引明确报错；多个／首尾分隔行、空表；Pandas可选分支另准备依赖。
- 原生回归：test/test_input.py；test/test_regression.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．无宽字符插件时识别 BEL 超链接（问题修复）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/460
- 原版现状：WIDE_CHARS_MODE=False时BEL结尾OSC8把URI算入宽度，ST正常；当前wcwidth开启时两者已正常，复现矩阵已区分。
- 交付目标：原生ANSI识别支持BEL和ST，不依赖可选wcwidth才能得到正确可见宽度。
- 影响模块：tabulate/__init__.py:_ansi_codes/_strip_ansi/_visible_width
- 兼容边界：不去掉实际链接序列；保留文本和URL，只在宽度计算时忽略控制部分。
- 正常验收：开启／关闭宽字符插件，两种终止符的docs单元格边框等宽。
- 异常／边界：相邻链接、链接中文字着色、混合终止符、无效未闭合序列和bytes输入。
- 原生回归：test/test_regression.py；test/test_internal.py；test/test_grapheme_clusters.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．序列格式参数统一接受 tuple（问题修复）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/434
- 原版现状：_expand_iterable 对 tuple+list 抛TypeError；rowalign tuple本轮已复现。
- 交付目标：先规范化合法有长序列再补齐，rowalign/maxheadercolwidths等统一支持tuple。
- 影响模块：tabulate/__init__.py:_expand_iterable 与参数展开
- 兼容边界：不把字符串当字符序列重新定义；保留各参数原有默认和截断规则。
- 正常验收：相同参数list/tuple输出字节一致，不修改调用方对象。
- 异常／边界：空tuple、较短／较长序列、非法元素和无长度iterator支持范围明确。
- 原生回归：test/test_api.py；test/test_output.py；test/test_textwrapper.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．自动换行尊重关闭数字推断（问题修复）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/428
- 原版现状：包装路径将 numparse 错传给 _type 的第二个has_invisible参数；80,443在disable_numparse=True时仍被int转换报错。
- 交付目标：按具名numparse传递并保持数字形文本原值，统一有无maxcolwidths语义。
- 影响模块：tabulate/__init__.py:_wrap_text_to_colwidths/_type
- 兼容边界：不改变默认数字识别规则；单列禁用列表与全局禁用一致。
- 正常验收：80,443、001、True、None等有无换行都不发生未授权类型转换。
- 异常／边界：ANSI数字串、列级disable列表、空串、missingval及真正数字格式化回归。
- 原生回归：test/test_regression.py；test/test_textwrapper.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．单元格换行保留有意空段落（问题修复）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/440
- 原版现状：_wrap_text_to_colwidths 过滤line.strip()==空，para1空行para2变成相邻两行，已实测。
- 交付目标：包装时保留显式空行与空白行的约定，不能吞掉段落分隔。
- 影响模块：tabulate/__init__.py:_wrap_text_to_colwidths/_CustomTextWrap
- 兼容边界：preserve_whitespace参数已有，按其规则处理空白，不修改纯单行输出。
- 正常验收：带空段落文本在grid与simple multiline模式保留空白显示行。
- 异常／边界：首尾空行、连续空行、仅空白、CRLF、maxheadercolwidths与ANSI内容。
- 原生回归：test/test_textwrapper.py；test/test_output.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．原生 Typst 表格格式（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/358
- 原版现状：tabulate_formats没有typst，调用方需自行生成标记。
- 交付目标：新增typst TableFormat，表头、对齐、文本转义和数值输出有明确规范。
- 影响模块：tabulate/__init__.py:_table_formats 与渲染辅助
- 兼容边界：不修改Markdown/LaTeX模式；不把任意cell内容当Typst代码执行。
- 正常验收：混合文本数值生成可直接用于Typst的table表达式及列对齐。
- 异常／边界：引号、反斜杠、方括号、换行、Unicode和空表；排版工具实际编译另列可选验证。
- 原生回归：test/test_output.py；test/test_api.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．纵向记录展示（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/257
- 原版现状：没有类似MySQL\G的每条记录逐字段输出格式；showindex只是行索引。
- 交付目标：新增vertical格式，每记录显示编号及字段名—值，适配少量宽记录。
- 影响模块：tabulate/__init__.py:_format_table 与新格式
- 兼容边界：普通二维格式不变，不把每记录重新调用tabulate导致格式／编号不一致。
- 正常验收：多字段客户记录逐项展示，长文本和多行字段保持关联。
- 异常／边界：无header用列索引、重复header、None、空行与SEPARATING_LINE行为明确。
- 原生回归：test/test_output.py；test/test_input.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．结构化对象的显式表格转换协议（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/309
- 原版现状：支持dataclass/映射/具名tuple，但Pydantic等需用户先dump；无通用注册转换协议。
- 交付目标：提供register_row_adapter(type,extractor)，把自定义模型转换为有序字段映射。
- 影响模块：tabulate/__init__.py:_normalize_tabular_data
- 兼容边界：不强制依赖Pydantic，不对任意对象盲调model_dump；普通dataclass保持。
- 正常验收：注册合成模型或可选Pydantic适配后headers=keys正确，实例原值不变。
- 异常／边界：异构模型字段、提取器错误、类继承优先级、重复注册和不可序列化值。
- 原生回归：test/test_input.py；test/test_api.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．列格式化回调（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/297
- 原版现状：floatfmt/intfmt只接受格式字符串/序列，没有收到原始值与列上下文的格式回调。
- 交付目标：增加cellformatters/数字formatter回调，规范化后、测宽前执行。
- 影响模块：tabulate/__init__.py:_format 与列处理
- 兼容边界：默认旧格式串保持；返回文本后不能再次数字推断破坏格式，不默认执行cell本身。
- 正常验收：金额回调输出固定币种，日期回调按指定规则显示，布局用最终宽度。
- 异常／边界：None策略、回调异常、ANSI/宽字符、列数不齐及原数据不变。
- 原生回归：test/test_output.py；test/test_api.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．显式小数点与千分位显示配置（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/291
- 原版现状：format可用locale敏感n但缺少每次调用独立的小数/分组符策略，不能安全靠全局setlocale切换。
- 交付目标：新增number_symbols配置，仅控制输出并让decimal对齐认识选定小数符。
- 影响模块：tabulate/__init__.py:_format/_afterpoint/_align_column
- 兼容边界：不改变默认输入数字推断；不在库内修改进程locale。
- 正常验收：1.234,50等显示与对齐正确，同进程两种格式互不污染。
- 异常／边界：负号、指数、Decimal、分组禁用、冲突符号、ANSI和missing值。
- 原生回归：test/test_output.py；test/test_internal.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．整张表的终端宽度预算（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/290
- 原版现状：maxcolwidths是逐列上限，没有自动将总宽度分配到固定终端列数。
- 交付目标：增加max_table_width及列最小/优先宽度策略，计算边框和padding后分配换行预算。
- 影响模块：tabulate/__init__.py:列宽计算／_wrap_text_to_colwidths
- 兼容边界：默认不读取终端；显式总宽度不足时清楚报错或按调用方选定溢出策略。
- 正常验收：80列预算下所有可见行<=80，中文/Emoji与ANSI按显示宽度计。
- 异常／边界：不可断数字、过窄header、多行、不同grid边框、索引列和空表。
- 原生回归：test/test_textwrapper.py；test/test_grapheme_clusters.py；test/test_output.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．分页输出与重复表头（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/285
- 原版现状：只一次输出全部表头，没有按页高度复用全表列宽和重复表头的接口。
- 交付目标：新增render_pages或repeat_header_every，保留逻辑行跨多显示行的分页规则。
- 影响模块：tabulate/__init__.py:_format_table 与新页输出辅助
- 兼容边界：不把每页独立推断列类型导致宽度跳动；默认单张输出保持。
- 正常验收：长报告每页重复header，列宽统一、每个数据行只出现一次。
- 异常／边界：单个超高cell、页尾分隔线、空页、无header及索引序号连续。
- 原生回归：test/test_output.py；test/test_input.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．带标题的业务行分组（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/254
- 原版现状：SEPARATING_LINE只能画线，不能携带跨列分组标题和层级。
- 交付目标：新增GroupHeading结构，作为展示行输出标题且不参与类型推断或索引。
- 影响模块：tabulate/__init__.py:_normalize_tabular_data/_format_table
- 兼容边界：原SEPARATING_LINE继续支持，组标题不冒充普通数据cell。
- 正常验收：地区标题分别位于所属数据上方，终端和HTML采用各自合法展示。
- 异常／边界：嵌套级别、空组、宽标题、header分页与showindex不串行。
- 原生回归：test/test_input.py；test/test_output.py
- 真实依赖：01

## 14．逐列边界的分隔线选择（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/220
- 原版现状：TableFormat可整体定义row separator，公开API没有逐边界mask；自定义callable是现有高级替代。
- 交付目标：增加column_separators配置，选择具体相邻列是否显示分隔符并同步横线接点。
- 影响模块：tabulate/__init__.py:_build_row/_build_line/TableFormat
- 兼容边界：默认现有样式保持；格式不支持该能力时明确拒绝，不生成歪斜框线。
- 正常验收：只在业务分区边界画竖线，表头／数据／水平线一致。
- 异常／边界：mask长度、索引列、隐藏首尾边框、多行和宽字符相接。
- 原生回归：test/test_output.py；test/test_internal.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．表头位置可为顶部／底部／两端（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/237
- 原版现状：所有格式通常把header放在顶部，没有公开header_position。
- 交付目标：新增受支持文本格式的header_position，并定义分隔线绘制。
- 影响模块：tabulate/__init__.py:_format_table
- 兼容边界：默认top；HTML继续以语义thead/tfoot表达，不简单复制<tr>到无效位置。
- 正常验收：长表bottom/both模式标签完整，列对齐与数量一致。
- 异常／边界：空数据、无header、SEPARATING_LINE、重复分页表头和不支持格式报错。
- 原生回归：test/test_output.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．单元格截断与省略标记（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/171
- 原版现状：maxcolwidths只换行；没有truncate到宽度并添加自定义ellipsis的原生选项。
- 交付目标：增加overflow=wrap/ellipsis，保留前/后或中间部分的明确策略。
- 影响模块：tabulate/__init__.py:_CustomTextWrap 与列宽适配
- 兼容边界：默认wrap保持；数字列是否截断必须显式，不能默默改变可读数值。
- 正常验收：长路径按末段保留、描述按开头保留，最终可见宽度符合上限。
- 异常／边界：省略符本身宽于预算、中文组合字符、ANSI闭合与OSC8链接不能截坏。
- 原生回归：test/test_textwrapper.py；test/test_grapheme_clusters.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．HTML 表格可访问性元数据（增强提案）

- 来源／场景：[tabulate/__init__.py:_html_begin_table_without_header/_html_row_with_attrs](https://github.com/astanin/python-tabulate/blob/268615a5c27dc40e5c22454c07b44d5c50410da0/tabulate/__init__.py)
- 原版现状：HTML转义已有，但没有caption、表头scope、row-header列等语义设置。
- 交付目标：增加HTML专属选项，输出caption和thead/tbody及明确scope属性。
- 影响模块：tabulate/__init__.py:HTML格式辅助
- 兼容边界：默认安全转义保持，unsafehtml不作为默认；属性值也要转义。
- 正常验收：caption与列/行表头被独立HTMLParser识别，数据顺序不变。
- 异常／边界：空表、含标签caption、重复列、特殊属性值及不支持的格式选项明确拒绝。
- 原生回归：test/test_output.py；test/test_regression.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．LaTeX 多行单元格的合法结构（增强提案）

- 来源／场景：https://github.com/astanin/python-tabulate/issues/283
- 原版现状：文本换行不能保证在LaTeX单元格中成为正确局部换行，需应用手写makecell/p列。
- 交付目标：增加latex_multiline明确模式，选定可解释的内嵌tabular或makecell语法。
- 影响模块：tabulate/__init__.py:LaTeX格式与多行映射
- 兼容边界：默认LaTeX行为保持，依赖额外宏包时在返回说明中明确；不启用latex_raw绕过转义。
- 正常验收：带两行文字和数值表生成合法局部结构，行列数保持。
- 异常／边界：百分号、&、下划线、反斜杠、空行、列宽与booktabs/longtable组合。
- 原生回归：test/test_output.py；可选TeX实际编译另记录环境
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．CLI 复用原生渲染配置（增强提案）

- 来源／场景：[tabulate/cli.py:_main/_pprint_file](https://github.com/astanin/python-tabulate/blob/268615a5c27dc40e5c22454c07b44d5c50410da0/tabulate/cli.py)
- 原版现状：CLI只透传少量参数，缺少disable_numparse、maxcolwidths、missingval等已存在库能力。
- 交付目标：增加明确--render-options JSON文件/参数，校验白名单并透传原生参数。
- 影响模块：tabulate/cli.py
- 兼容边界：不把配置内容eval，不允许导入回调；旧命令行优先级保持并文档化。
- 正常验收：CSV中的001在disable_numparse后保真，长文本按指定列宽输出文件。
- 异常／边界：未知键、类型错、JSON坏、选项冲突和缺文件退出码清楚且输出不误报成功。
- 原生回归：test/test_cli.py；test/test_api.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．CLI 显式选择 JSONL 嵌套列与标签（增强提案）

- 来源／场景：[tabulate/cli.py:_read_jsonl_file 与 headers解析](https://github.com/astanin/python-tabulate/blob/268615a5c27dc40e5c22454c07b44d5c50410da0/tabulate/cli.py)
- 原版现状：JSONL仅整行载入；--headers逗号/冒号简单拆分不能表示这些字符，且没有嵌套字段选择。
- 交付目标：新增--columns-json有序列规格，路径序列取嵌套字段并给显式显示名。
- 影响模块：tabulate/cli.py:JSONL读取与header处理
- 兼容边界：现有--headers字符串保持；不执行JsonPath表达式，只读键/数组位置。
- 正常验收：客户address.city和订单qty输出指定顺序，显示名可含逗号/冒号。
- 异常／边界：缺失路径默认值、数组越界、类型不一致、坏JSONL行号及重复显示名政策。
- 原生回归：test/test_cli.py；test/test_input.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
