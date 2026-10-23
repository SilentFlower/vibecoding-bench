# sqlparse：二十步真实工程迭代路线

固定 [andialbrecht/sqlparse@60cdc649726bf1bc4f1b336050560b336da715ec](https://github.com/andialbrecht/sqlparse/tree/60cdc649726bf1bc4f1b336050560b336da715ec)，见[单仓审查](./sqlparse.md)。本轮只研究，不实施；9项原版复现修复提案与11项明确增强提案。新API名称是拟议契约，不能视作现版能力。

每步是一个完整交付，包含代码、测试、文档及失败修复。全部SQL只做本地文本解析/格式化，CLI只改研究脚本自己创建的临时文件，不执行SQL或连接数据库。每项对应一个observations-result.json编号与真实源码路径。

## 01．格式化失败时保留原文件

- **类型与来源**：已复现修复提案；本地开发者以 --in-place 批量格式化SQL，参数错误时需保留输入。
- **原版现状与证据**：01_inplace_before_validation：--indent_width 0 退出1并报告Invalid options，但原来9字节select 1;已被截断为空。_process_file在validate_options前用w打开目标。
- **交付目标**：先验证选项并在内存完成格式化，再以同目录临时文件替换本轮目标；格式化或写入失败保留原文件。
- **影响模块**：sqlparse/cli.py。
- **兼容边界**：成功输出与原选项保持；只操作显式指定本地文件，stdin不支持in-place；不把错误目标当成功文件计数。
- **正常验收**：合法格式化正确更新，非法indent_width保持原文件字节、给非零退出码。
- **边界验收**：格式化异常、空文件、写入/替换异常、多个文件中单项失败和临时文件清理；stdout与outfile路径不提前截断。
- **原生回归**：tests/test_cli.py。
- **实际依赖**：无；标准库tempfile/os。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/cli.py)。

## 02．CLI布尔参数的显式真值语义

- **类型与来源**：已复现修复提案；用户写--comma_first False或--compact False，预期关闭对应排版。
- **原版现状与证据**：02_cli_bool_options：两项传字符串False均得到True；create_parser使用type=bool。它们是同一CLI布尔解析缺陷族，只计一步。
- **交付目标**：改为有清晰开关或严格布尔文字的参数设计，提供反向关闭形式与兼容过渡，拒绝未知文字。
- **影响模块**：sqlparse/cli.py。
- **兼容边界**：Python格式化API布尔语义不变；对已有显式True/False用法定义兼容解析，不静默把任意非空串解释为True。
- **正常验收**：True/False及正反开关分别得到正确值，并影响真实CLI排版。
- **边界验收**：大小写、0/1、空字符串、重复参数和非法文字的取舍有确定错误；--help描述与实际一致。
- **原生回归**：tests/test_cli.py、tests/test_format.py。
- **实际依赖**：无；标准库argparse。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/cli.py)。

## 03．完成公开right_margin排版选项

- **类型与来源**：已复现修复提案；开发者使用已公开的右边界选项格式化长商品查询。
- **原版现状与证据**：03_right_margin：right_margin=25直接NotImplementedError；filters/right_margin.py.process明确未实现，上游test_format_right_margin标记xfail Needs fixing。
- **交付目标**：完成RightMarginFilter，在可断开的语法边界换行并保持缩进，不改变SQL字符串/标识符内容。
- **影响模块**：sqlparse/filters/right_margin.py、sqlparse/formatter.py。
- **兼容边界**：未设置right_margin时输出不变；不能为了达到列宽切开字符串或quoted identifier；超长不可分token允许超过边界并说明。
- **正常验收**：长SELECT列表在合法位置折行，格式化后非空白token序列一致，原xfail变真实通过。
- **边界验收**：窄边界、Unicode显示宽度策略、注释、嵌套表达式、单个超长值和多语句回归。
- **原生回归**：tests/test_format.py。
- **实际依赖**：无；现有TokenList/FilterStack；不依赖步骤06分页规则。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/right_margin.py)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/formatter.py)。

## 04．多语句Python输出的语法与内容一致

- **类型与来源**：已复现修复提案；文档工具把多份普通SQL转成Python字符串赋值，需产生可解析源码。
- **原版现状与证据**：04_python_output：reindent=True/output_format=python的两语句样本ast.parse报unterminated string literal；对应原生测试标记xfail。
- **交付目标**：修复OutputPythonFilter跨语句的换行与引号组合，使每个变量赋值保持有效语法且字符串值等于对应SQL内容。
- **影响模块**：sqlparse/filters/output.py、sqlparse/filters/others.py。
- **兼容边界**：现有单语句与sql/sql2命名保持；沿用现有字符串转义规则，不改变SQL语义或执行SQL。
- **正常验收**：ast.parse能解析多语句输出，控制端以AST读取常量拼接后与预期SQL逐条比对；原xfail通过。
- **边界验收**：前后空白、换行语句分隔、单双引号、Unicode、空语句和PHP输出原有回归；验收只解析源码不执行生成代码。
- **原生回归**：tests/test_format.py。
- **实际依赖**：无；标准库ast仅用于冻结验收。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/output.py)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/others.py)。

## 05．READ WRITE事务开始语句拆分

- **类型与来源**：已复现修复提案；Redshift脚本编辑器需要将BEGIN READ WRITE、查询与END分别展示。
- **原版现状与证据**：05_readwrite_split：BEGIN READ WRITE; SELECT 1; END;只得到1条；StatementSplitter已有BEGIN TRANSACTION/WORK等特判但未识别READ WRITE。
- **交付目标**：扩展事务开始识别，区分READ WRITE/READ ONLY等事务属性与过程BEGIN...END，按真实分号形成语句。
- **影响模块**：sqlparse/engine/statement_splitter.py、sqlparse/keywords.py。
- **兼容边界**：既有过程块、嵌套控制结构和BEGIN TRANSACTION保持；不把所有BEGIN后内容无条件当事务。
- **正常验收**：样本得到BEGIN READ WRITE;、SELECT 1;、END;三条，去分号模式一致。
- **边界验收**：大小写、注释间隔、READ ONLY、普通过程BEGIN块与BEGIN;原有边界验证。
- **原生回归**：tests/test_split.py。
- **实际依赖**：无；纯文本拆分，不连接数据库。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/843)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/statement_splitter.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/keywords.py)。

## 06．分页子句的整体对齐

- **类型与来源**：已复现修复提案；本地SQL阅读需要OFFSET/FETCH分页子句保持连贯。
- **原版现状与证据**：06_paging_alignment：原版aligned格式把ONLY孤立为最后一行；split_words缺OFFSET/FETCH等相关分页边界。
- **交付目标**：识别OFFSET...ROWS及FETCH NEXT/FIRST...ROWS ONLY的逻辑组，不把ONLY当独立行；定义多行时的明确折行位置。
- **影响模块**：sqlparse/filters/aligned_indent.py、sqlparse/keywords.py。
- **兼容边界**：普通ORDER BY/LIMIT、标识符同名和无分页查询输出保持；不是把所有名为ONLY的token硬拼接。
- **正常验收**：官方样本的ONLY与ROWS保持一行，OFFSET与主体子句有一致对齐。
- **边界验收**：参数占位、FETCH FIRST、单行无ORDER BY、嵌套查询和已有right_margin组合回归。
- **原生回归**：tests/test_format.py、tests/test_regressions.py。
- **实际依赖**：无；可独立于步骤03，二者组合另跑回归。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/842)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/aligned_indent.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/keywords.py)。

## 07．函数后的隐式别名分组

- **类型与来源**：已复现修复提案；查询按year/month做EXTRACT别名，不写AS也应形成同级SELECT项。
- **原版现状与证据**：07_function_aliases：无AS的year/month被视为关键字，三个列逐渐向右漂移；加AS后列正常对齐。group_aliased只接受Identifier作为后项。
- **交付目标**：在合法表达式后的别名上下文识别可作名字的关键字，形成Identifier以供列格式化，同时保留函数内部year/month关键字。
- **影响模块**：sqlparse/engine/grouping.py、sqlparse/sql.py、sqlparse/filters/reindent.py。
- **兼容边界**：不能全局把year/month降为Name；显式AS、EXTRACT内部from以及真正语句关键字不误吞。
- **正常验收**：有AS/无AS样本均有三项同级列和正确get_alias，重排不会逐列增缩进。
- **边界验收**：quoted别名、函数嵌套、别名同名关键字、ORDER BY与缺失别名场景回归。
- **原生回归**：tests/test_grouping.py、tests/test_format.py、tests/test_parse.py。
- **实际依赖**：无；现有上下文分组。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/781)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/grouping.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/sql.py)；[依据4](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/reindent.py)。

## 08．DDL列定义的稳定排版模式

- **类型与来源**：增强提案；商品表DDL含列COMMENT与约束，开发者需要同级列缩进稳定。
- **原版现状与证据**：08_ddl_layout：三列和PRIMARY KEY样本缩进依次47/75/100，受一般IdentifierList偏移累加影响；普通reindent未给DDL专门布局契约。
- **交付目标**：增加明确DDL排版策略，识别CREATE TABLE列列表、列注释和表级约束，各列保持同层级，保留表达式内部结构。
- **影响模块**：sqlparse/filters/reindent.py、sqlparse/engine/grouping.py。
- **兼容边界**：显式采用新模式；不宣称完整验证DDL语法，不改字符串COMMENT内容或CREATE TABLE AS SELECT普通查询规则。
- **正常验收**：字段名/类型/COMMENT逐列同级，PRIMARY KEY与UNIQUE约束在同级独立行。
- **边界验收**：类型精度逗号、函数默认值、generated列、嵌套CHECK、Unicode注释与复合约束不被当列分隔。
- **原生回归**：tests/test_format.py、tests/test_grouping.py。
- **实际依赖**：无；现有token树，不引入数据库方言执行器。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/805)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/reindent.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/grouping.py)。

## 09．成对反斜线字符串的词法边界

- **类型与来源**：已复现修复提案；普通SQL编辑器要正确高亮两个包含反斜线的字符串值。
- **原版现状与证据**：09_backslash_literals：SELECT后两个同样字面量被合成一个String.Single及多个Error；keywords.py单引号规则没有正确处理成对反斜线的结束位置。
- **交付目标**：按明确的转义约定识别连续反斜线与闭引号，保证两个值各自成token；保留原文本不解码业务内容。
- **影响模块**：sqlparse/keywords.py、sqlparse/lexer.py。
- **兼容边界**：已有双单引号与单个转义引号语义回归；涉及方言差异时用显式策略，不任意改变所有字面量约定。
- **正常验收**：官方普通两值样本得到两个String.Single与中间逗号，没有Error，split仍是一条语句。
- **边界验收**：奇偶数反斜线、尾部转义、字符串内逗号/分号、Unicode及未完成编辑输入有确定结果。
- **原生回归**：tests/test_tokenize.py、tests/test_split.py、tests/test_regressions.py。
- **实际依赖**：无；纯本地文本词法处理。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/814)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/keywords.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/lexer.py)。

## 10．识别REFRESH语句类型

- **类型与来源**：增强提案；报表编辑器按语句类型标注物化视图刷新文本。
- **原版现状与证据**：10_refresh_statement：REFRESH MATERIALIZED VIEW order_summary;得到UNKNOWN；get_type只查首个DML/DDL或CTE，MATERIALIZED词条已有，REFRESH没有对应分类。
- **交付目标**：为REFRESH及相关语句前缀建立明确类型识别，返回稳定REFRESH，保留非验证解析定位。
- **影响模块**：sqlparse/keywords.py、sqlparse/sql.py。
- **兼容边界**：其他UNKNOWN不盲目按第一个Name猜类型；现有SELECT/INSERT/CREATE与CTE规则不变。
- **正常验收**：大小写和前置注释下返回REFRESH，普通物化视图名仍是Identifier。
- **边界验收**：REFRESH作为列名/别名、残缺文本、CONCURRENTLY等可选修饰语和多语句不误分组。
- **原生回归**：tests/test_keywords.py、tests/test_parse.py。
- **实际依赖**：无；仅文本分类。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/797)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/keywords.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/sql.py)。

## 11．每次解析注入独立Lexer

- **类型与来源**：增强提案；同一编辑器同时支持两套业务关键字，不能污染进程全局单例。
- **原版现状与证据**：11_lexer_injection：独立Lexer能识别PRODUCTSCAN而全局不识别，但FilterStack只接strip_semicolon，parse无lexer入口；run固定调用全局tokenize。
- **交付目标**：为FilterStack及可选择的顶层parse/format/split调用传入Lexer实例，整条过滤链一致使用该实例。
- **影响模块**：sqlparse/engine/filter_stack.py、sqlparse/lexer.py、sqlparse/__init__.py。
- **兼容边界**：不传时继续默认单例；不在调用后重置全局对象，保留自定义Lexer的现有方法协议。
- **正常验收**：两个独立lexer并行/交错处理相同文本得到各自token类型，默认解析不受影响。
- **边界验收**：流式输入、bytes编码、grouping/format/split各入口、子类Lexer和非法对象均有明确契约。
- **原生回归**：tests/test_tokenize.py、tests/test_parse.py、tests/test_split.py、tests/test_format.py。
- **实际依赖**：无；已有Lexer；所有入口的一致性属于同一交付，不拆步。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/806)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/filter_stack.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/lexer.py)；[依据4](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/__init__.py)。

## 12．可选择的原始token源位置

- **类型与来源**：增强提案；中文SQL编辑器需要高亮和选区定位，避免每次从头累计长度。
- **原版现状与证据**：12_source_positions：Token无start/end；get_token_at_offset已有按长度查找单个offset，但不能直接查询每个token原始范围。
- **交付目标**：新增可选择位置输出协议或旁路SourceMap，记录字符起止与行列，对分组范围给出只读聚合。
- **影响模块**：sqlparse/lexer.py、sqlparse/sql.py、sqlparse/engine/statement_splitter.py。
- **兼容边界**：原tokenize二元组协议默认保持；原始位置与格式化后位置明确区分，修改token后不得继续冒充有效原位置信息。
- **正常验收**：中文和多行样本每个token范围切片等于原value，分组范围覆盖原子token。
- **边界验收**：CRLF、组合字符、bytes解码、空token、注释及多语句偏移连续；字符位置不伪称UTF-8字节偏移。
- **原生回归**：tests/test_tokenize.py、tests/test_parse.py、tests/test_grouping.py。
- **实际依赖**：无；标准库位置索引；不改变Token默认内存成本。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/793)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/lexer.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/sql.py)；[依据4](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/statement_splitter.py)。

## 13．显式token大小写匹配策略

- **类型与来源**：增强提案；业务查询工具需按规范化名称匹配标识符，或精确匹配关键字原写法。
- **原版现状与证据**：13_match_case_policy：Keyword的SELECT大小写匹配本来就成功；Name Products对products不匹配。Token.match没有case选项。官方#795陈述的关键字大小写限制不成立，不能照抄成缺陷。
- **交付目标**：增加明确case_sensitive/normalization策略，覆盖普通与regex匹配，保留默认按token种类的现有行为。
- **影响模块**：sqlparse/sql.py。
- **兼容边界**：默认关键字不敏感、标识符敏感保持；不得在匹配时改变token原value；quoted标识符的语义由调用者显式决定。
- **正常验收**：同一个Name在不敏感模式成功、敏感模式失败；Keyword在精确模式区分原始写法。
- **边界验收**：Unicode大小写、regex flags、values迭代器、None和不匹配ttype保持确定行为。
- **原生回归**：tests/test_tokenize.py、tests/test_parse.py。
- **实际依赖**：无；标准库re；此为增强，不是#795原叙述的修复。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/795)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/sql.py)。

## 14．非执行型SQL指纹助手

- **类型与来源**：增强提案；本地报表库需要按查询形状分组，忽略业务字面量和普通注释。
- **原版现状与证据**：14_query_fingerprint：无fingerprint入口；strip_comments能清注释但保留1/2/56等字面量，当前需自行遍历token。
- **交付目标**：新增独立fingerprint，按显式策略规范空白/关键字并替换字面量，支持IN列表形状策略，返回规范文本或摘要。
- **影响模块**：sqlparse/__init__.py、sqlparse/filters/tokens.py、sqlparse/engine/filter_stack.py。
- **兼容边界**：只用于统计分组，不生成可执行参数化SQL，不承诺语义相等；保留标识符和参数占位区别，默认不更改原输入。
- **正常验收**：相同结构不同商品id得到相同指纹，不同表/操作保留不同指纹。
- **边界验收**：字符串内注释符、NULL/布尔、负数、日期、美元引号、已有占位、空列表与嵌套IN的策略明确。
- **原生回归**：tests/test_format.py、tests/test_tokenize.py。
- **实际依赖**：无；已有token类型与标准库hashlib。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/776)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/__init__.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/tokens.py)；[依据4](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/filter_stack.py)。

## 15．CLI只读格式检查与差异展示

- **类型与来源**：增强提案；仓库CI希望判断SQL是否满足排版并看到diff，开发机不应先改文件。
- **原版现状与证据**：15_cli_review_mode：--check和--diff均argparse退出2。已有CLI只输出或写文件，不能直接用状态表示是否需要格式化。
- **交付目标**：提供配套check/diff工作流：只读输入，区分一致/需修改/错误退出码，diff显示统一差异和文件名。
- **影响模块**：sqlparse/cli.py。
- **兼容边界**：默认格式化模式不变；不与in-place同时启用；不把内容差异当格式化异常，stdin有明确标签。
- **正常验收**：已规范文件返回0，待格式化返回约定非零并可显示统一diff，源文件摘要不变。
- **边界验收**：空文件、多个文件、编码错误、无末尾换行、Unicode路径和部分错误时的总状态明确。
- **原生回归**：tests/test_cli.py。
- **实际依赖**：无；标准库difflib；check与diff是同一审阅交付，不拆两步。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/cli.py)。

## 16．保留本地文件换行与结尾约定

- **类型与来源**：增强提案；跨平台SQL仓库需要保留CRLF和末尾换行，避免只有排版外的噪声差异。
- **原版现状与证据**：16_newline_preservation：BOM+CRLF两句文件in-place后BOM仍保留，但CRLF变LF且末尾换行消失。不得声称BOM本来丢失。
- **交付目标**：增加明确newline/terminal-newline策略：preserve时探测原文件并保留，显式lf/crlf可规范化；BOM与编码策略清楚分离。
- **影响模块**：sqlparse/cli.py、sqlparse/filters/others.py。
- **兼容边界**：默认旧输出可维持；preserve不改字符串内部换行内容；UTF-8 BOM现有保留能力回归。
- **正常验收**：CRLF和LF文件各按preserve输出，末尾一个换行或无换行按策略保持。
- **边界验收**：混合换行、空文件、stdin/stdout、BOM、编码指定和字符串内真实换行的取舍明确；与步骤01原子写入组合回归。
- **原生回归**：tests/test_cli.py、tests/test_format.py。
- **实际依赖**：无；标准库文本/二进制IO；不以步骤01为必要前提。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/cli.py)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/others.py)。

## 17．带引号信息的多段标识符读取

- **类型与来源**：增强提案；编辑器展示db.store.products的各层名称，不能只取parent和real_name两端。
- **原版现状与证据**：17_identifier_parts：原接口返回parent=db、real_name=products、alias=p，缺get_name_parts，store需手工解析；已有两端查询不算新增。
- **交付目标**：新增get_name_parts，返回每段原始文本、去引号值与quote种类，明确别名、通配符和函数不属于名称段。
- **影响模块**：sqlparse/sql.py、sqlparse/engine/grouping.py。
- **兼容边界**：get_parent_name/get_real_name原行为保持；不按简单split点号破坏引号内点号，不尝试解析数据库语义。
- **正常验收**：三段标识符依次返回db/store/products，quoted带点名字仍是一段，alias独立。
- **边界验收**：双引号/backtick/方括号、转义引号、空段、星号、类型转换和部分编辑输入均有受支持/不支持的明确结果。
- **原生回归**：tests/test_parse.py、tests/test_grouping.py。
- **实际依赖**：无；已有token树。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/sql.py)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/grouping.py)。

## 18．真正分块读取的SQL流解析

- **类型与来源**：增强提案；本地大型SQL导出查看器希望首条语句出现前不先读完整输入。
- **原版现状与证据**：18_incremental_read：next(parsestream)前原Lexer对TextIO调用read(-1)，29字节样本已全部读取；现有parsestream仅输出生成器，不是输入分块读取。
- **交付目标**：增加明确增量输入接口，接受chunk迭代器或有界read，保留跨chunk字符串/注释/美元引号/语句状态，逐句输出。
- **影响模块**：sqlparse/lexer.py、sqlparse/engine/statement_splitter.py、sqlparse/__init__.py。
- **兼容边界**：现有普通tokenize/parsestream保持；单个超长token仍可能需要相应内存，不能承诺恒定内存；不连接真实数据库。
- **正常验收**：多句普通文件首条输出前只消耗有界前缀，所有chunk划分下token值和split结果与整串相同。
- **边界验收**：Unicode解码边界、分号在字面量内、CRLF分界、未结束最后语句、read异常和关闭所有权明确。
- **原生回归**：tests/test_tokenize.py、tests/test_split.py、tests/test_parse.py。
- **实际依赖**：无；标准库增量解码；可使用默认Lexer，独立于步骤11自定义注入。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/lexer.py)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/engine/statement_splitter.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/__init__.py)。

## 19．未完成括号表达式的格式化诊断

- **类型与来源**：已复现修复提案；SQL编辑器用户尚未写完括号表达式时，格式化不应漏出内部IndexError。
- **原版现状与证据**：19_incomplete_parentheses：( AS )配strip_whitespace=True实测IndexError；StripWhitespaceFilter._stripws_parenthesis直接访问tokens[1]/[-2]。
- **交付目标**：对缩短后的括号组做长度及边界检查，保持可处理输入或返回带上下文的SQLParseError，避免内部索引异常。
- **影响模块**：sqlparse/filters/others.py、sqlparse/sql.py。
- **兼容边界**：仍是非验证解析器，不把所有不完整SQL升级为严格语法拒绝；正常括号空白清理行为不变。
- **正常验收**：已复现输入不再IndexError，输出保留有意义token或明确SQLParseError；完整括号表达式仍正确。
- **边界验收**：空括号、只剩开/闭括号、嵌套空组、前后注释和多次格式化幂等回归。
- **原生回归**：tests/test_format.py、tests/test_regressions.py。
- **实际依赖**：无；同一缺陷族全部边界只计一步。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/issues/885)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/filters/others.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/sql.py)。

## 20．可选择的严格格式选项校验

- **类型与来源**：增强提案；业务工具拼错keyword_case时需要立即定位，避免静默输出未格式化文本。
- **原版现状与证据**：20_strict_options：keyword_cases=upper被忽略，返回select 1；正确keyword_case返回SELECT 1，validate_options无strict模式。
- **交付目标**：增加显式严格选项校验与公开支持键清单；未知键报告近似建议，区分CLI元参数和formatter参数。
- **影响模块**：sqlparse/formatter.py、sqlparse/__init__.py、sqlparse/cli.py。
- **兼容边界**：默认可保留宽松行为；CLI先提取自己的filename/outfile等参数，不把现有vars(args)误报；扩展filter选项有明确注册边界。
- **正常验收**：错拼keyword_cases在strict模式得到可读错误和keyword_case建议，合法组合仍输出正确。
- **边界验收**：未知None值、多个未知键、别名、第三方扩展和组合选项验证顺序明确；错误不改输入文件。
- **原生回归**：tests/test_format.py、tests/test_cli.py。
- **实际依赖**：无；标准库difflib可用于建议；独立于步骤01的文件写入修复。 功能步骤依赖：无。
- **来源链接**：[依据1](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/formatter.py)；[依据2](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/__init__.py)；[依据3](https://github.com/andialbrecht/sqlparse/blob/60cdc649726bf1bc4f1b336050560b336da715ec/sqlparse/cli.py)。

## 原生预期失败与未来独立验收

本轮完整原生测试为506通过、1 XPASS、2个上游xfail，分别对应步骤03/04；两项未修复，不能报告509通过。未来实现后要把对应原生xfail转换为真实通过并保持其他测试，不通过删除/新加xfail放行。冻结验收应独立调用候选原生API/CLI，观察token类型/顺序、拆分结果、格式文本、AST可解析性与临时文件字节及关闭行为，累计回归此前接受能力。依赖离线准备、冻结用例、候选实现与平台接入均未完成。
