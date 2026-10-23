# bibtexparser：二十步真实工程迭代路线

固定 [sciunto-org/python-bibtexparser@af329ca482b29691caff69cb2f8e6099670a105f](https://github.com/sciunto-org/python-bibtexparser/tree/af329ca482b29691caff69cb2f8e6099670a105f)，原生证据见 [单仓审查](./bibtexparser.md)。以下均为逐仓分析提出的本地工程增强提案，尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．交叉引用字段继承

- **来源／场景**：会议论文用 crossref 引用论文集公共字段；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/interpolate.py)。
- **原版缺口**：interpolate.py 仅解析字符串宏并有 Crossref TODO；实测子论文不继承 booktitle/year
- **交付及模块**：新增显式 ResolveCrossrefMiddleware，按父子关系继承缺失字段并记录来源；`bibtexparser/middlewares/interpolate.py`, `bibtexparser/library.py`。
- **兼容与实际依赖**：默认解析栈不变；子项显式字段优先；不把README概述当已实现；步骤依赖：无。
- **正常验收**：子论文继承父书名和年份，原有title不覆盖
- **异常／边界验收**：缺父项、多级引用、环、大小写key及重复父项有明确错误；不修改原库除非明确允许inplace
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 02．重复字段提取字符串宏

- **来源／场景**：一个期刊名重复几十次希望规范为 @string；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/interpolate.py)。
- **原版缺口**：只有 ResolveStringReferences，源码TODO注明反向替换尚无；原版重复值各自写出
- **交付及模块**：新增反向宏提取middleware，接受字段白名单、出现阈值和命名策略；`bibtexparser/middlewares/interpolate.py`, `bibtexparser/model.py:String`。
- **兼容与实际依赖**：显式启用；不替换title中的局部子串，不改变不在白名单的字段；步骤依赖：无。
- **正常验收**：重复journal写成一次@string及多个裸引用，重新解析语义等价
- **异常／边界验收**：已有宏重名、大小写冲突、宏值本身含表达式和一次性字段不错误提升
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 03．引用键整体重命名

- **来源／场景**：参考文献编辑器把P改成Proceedings2026需同步引用；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/library.py)。
- **原版缺口**：Entry.key可直接赋值，Library有remove/replace但无rename_key或引用重写
- **交付及模块**：提供原子rename_key，更新索引及明确crossref/xdata等引用字段，返回修改清单；`bibtexparser/library.py:Library`, `bibtexparser/model.py:Entry`。
- **兼容与实际依赖**：不擅自改普通文本；可配置引用字段；保留block位置与raw来源；步骤依赖：无。
- **正常验收**：改键后entries_dict只含新键，子项引用同步且write/read可往返
- **异常／边界验收**：目标重名、未知旧键、失败块及批量互换键要么全部成功要么全库不变
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 04．文献重复识别与合并

- **来源／场景**：同一DOI以两个不同citation key导入；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/library.py)。
- **原版缺口**：Library.add仅处理相同key，未提供按文献身份merge_duplicates
- **交付及模块**：增加按明确DOI或用户选择字段识别重复，预览后按字段冲突策略合并；`bibtexparser/library.py`, `bibtexparser/model.py:Entry`。
- **兼容与实际依赖**：不同标题相似不自动合并；原始条目与来源保留可追溯；不等同相同key错误恢复；步骤依赖：无。
- **正常验收**：两个相同规范DOI的记录生成一条预览，合并补全缺失卷期
- **异常／边界验收**：不同DOI、相同title不同year、冲突author、缺DOI与重复候选组均不误合
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 05．条目类型字段校验

- **来源／场景**：投稿前检查article缺journal、book缺publisher等；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/model.py)。
- **原版缺口**：解析只建立Field/Entry结构，保留任意字段；无validate_entries模式
- **交付及模块**：提供版本化可配置类型规则，报告缺必填、互斥/替代组和未知字段；`bibtexparser/model.py:Entry`, `bibtexparser/library.py`。
- **兼容与实际依赖**：默认容错解析保持；区分BibTeX与BibLaTeX配置，不擅自删除字段；步骤依赖：无。
- **正常验收**：article缺journal给定位报告，author/editor替代组按所选格式通过
- **异常／边界验收**：未知entry_type、自定义规则、空字段、继承后的缺字段与原始缺字段分别说明
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 06．书目标识符规范化

- **来源／场景**：多来源导入带DOI URL、ISBN连字符；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/middleware.py)。
- **原版缺口**：原版字段按普通字符串处理，内建middleware没有标识符规范化
- **交付及模块**：新增可选择DOI/ISBN的规范化middleware，保留原值并给出结构校验结果；`bibtexparser/middlewares/middleware.py`, `bibtexparser/model.py:Field`。
- **兼容与实际依赖**：只做本地语法/ISBN校验，不调用出版商或网络查询；不改变未知标识符；步骤依赖：无。
- **正常验收**：DOI前缀URL转规范doi，合法ISBN可输出选定连字符风格
- **异常／边界验收**：尾部标点、非法ISBN校验位、多值字段、Unicode空格及未知scheme不静默修复
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 07．页码范围规范化

- **来源／场景**：编辑期刊页码 12-19 或 e123；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/middleware.py)。
- **原版缺口**：无pages专用middleware，字段原样保存
- **交付及模块**：提供选定的pages规范化，把明确数字范围转BibTeX双连字符并保留电子页码；`bibtexparser/middlewares/middleware.py`, `bibtexparser/model.py:Field`。
- **兼容与实际依赖**：只作用pages字段；不替换title中的连字符，不猜测小数范围；步骤依赖：无。
- **正常验收**：12-19与12–19按选项统一成12--19，单页和e123保持
- **异常／边界验收**：罗马页、断续多范围、倒序、空页及已规范值幂等，复杂未知写法明确保留
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 08．BibLaTeX日期区间解析

- **来源／场景**：文献包含date=2026-10或2026-10/2026-11；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/month.py)。
- **原版缺口**：有month变换但没有date语义解析；year/month不等同完整日期区间
- **交付及模块**：新增ParseBiblatexDates生成带精度的日期/范围对象，并提供可逆unparse；`bibtexparser/middlewares/month.py`, `bibtexparser/model.py:Field`。
- **兼容与实际依赖**：显式开启且与传统year/month分离；不把年月份补为第一天伪造精度；步骤依赖：无。
- **正常验收**：年、年月、完整日与开放端区间往返保留原精度
- **异常／边界验收**：非法闰日、未知日期标记、区间倒序与year冲突给报告；默认解析不受影响
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 09．保护括号的关键词拆分

- **来源／场景**：keywords中逗号分隔但花括号保护短语内逗号；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/middleware.py)。
- **原版缺口**：现有名称拆分仅针对author/editor，无SplitKeywords
- **交付及模块**：新增关键词拆分与合并middleware，按明确分隔符和括号层次处理；`bibtexparser/middlewares/middleware.py`, `bibtexparser/model.py:Field`。
- **兼容与实际依赖**：不复用按and分人的作者算法；默认字符串仍保持，逆变换可写BibTeX；步骤依赖：无。
- **正常验收**：alpha,{beta,gamma},delta得到三个关键词，重新合并后语义不变
- **异常／边界验收**：嵌套括号、转义逗号、空项、重复词和不平衡括号给确定处理
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 10．可预览引用键生成

- **来源／场景**：从无规范键的导入库生成AuthorYearTitle式键；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/middlewares/names.py)。
- **原版缺口**：已有NameParts但Library无generate_citation_keys，手工拼接与冲突后缀由调用方实现
- **交付及模块**：新增配置化键生成器，支持作者/组织/年份/标题词、预览及稳定冲突后缀；`bibtexparser/middlewares/names.py:NameParts`, `bibtexparser/library.py`。
- **兼容与实际依赖**：默认不覆盖已有键，写入必须显式选择；与第03步引用同步机制复用；步骤依赖：03。
- **正常验收**：同一输入反复预览键一致，两篇同作者同年得到稳定a/b后缀
- **异常／边界验收**：缺作者、组织名、非拉丁文字、受保护title词、已有后缀冲突不产生空键或重名
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 11．结构化文献筛选

- **来源／场景**：只导出2020年后某期刊包含特定关键词的条目；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/library.py)。
- **原版缺口**：Library提供entries/entries_dict但无query；调用方只能循环并自管字段类型
- **交付及模块**：提供可组合类型明确的谓词筛选，返回稳定顺序视图/复制选项；`bibtexparser/library.py`, `bibtexparser/model.py:Entry`。
- **兼容与实际依赖**：不执行输入字符串代码；不默认修改原库；区分未设字段与空字段；步骤依赖：无。
- **正常验收**：按entry_type、年份范围、journal和关键词组合得到精确子集
- **异常／边界验收**：非法年份、缺字段、大小写规则、多个值及零结果保持明确，视图修改规则可检验
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 12．CSL JSON交换

- **来源／场景**：本地引文工具使用CSL JSON书目；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/entrypoint.py)。
- **原版缺口**：原生入口只处理BibTeX，无to_csl_json或对称导入
- **交付及模块**：一次交付常见类型字段映射、NameParts作者和日期映射及未知字段保留区；`bibtexparser/entrypoint.py`, `bibtexparser/model.py`, `bibtexparser/middlewares/names.py`。
- **兼容与实际依赖**：不生成最终引文样式、不接外部服务；保留可诊断的有损映射；步骤依赖：无。
- **正常验收**：article/book的作者、标题、DOI和日期导出后再导入保持已声明字段语义
- **异常／边界验收**：组织作者、多语言标题、不支持类型、复合日期和多值字段报告映射损失
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 13．RIS本地导入导出

- **来源／场景**：馆员有RIS离线导出需转BibTeX；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/entrypoint.py)。
- **原版缺口**：没有parse_ris/write_ris；BibTeX Splitter不理解TY/ER标签
- **交付及模块**：增加独立RIS解析/写入模块，映射重复AU、类型、页码及DOI并保留未知标签；`bibtexparser/entrypoint.py`, `bibtexparser/model.py`。
- **兼容与实际依赖**：不把RIS文本交给原Splitter猜格式；BibTeX默认入口不变；步骤依赖：无。
- **正常验收**：含两位作者的JOUR记录读写后作者顺序和关键字段一致
- **异常／边界验收**：缺ER、续行、重复单值标签、未知TY、Unicode和多个记录的边界明确
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 14．带依赖的书目子集导出

- **来源／场景**：只交付引用的三篇论文，同时保留所需@string和父论文集；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/library.py)。
- **原版缺口**：Library无subset，直接筛entries会丢宏/父引用；现有字符串解析可消除部分依赖但不等于导出闭包
- **交付及模块**：提供按entry key取依赖闭包，包含引用父项和仍使用的宏，保留源顺序；`bibtexparser/library.py`, `bibtexparser/middlewares/interpolate.py`。
- **兼容与实际依赖**：不导出未引用的无关条目；可选择解析继承后扁平输出；不将注释当必需文献；步骤依赖：无。
- **正常验收**：只选子论文仍能带父论文集和所需期刊宏，独立解析后值可用
- **异常／边界验收**：环与缺依赖、嵌套宏、重复引用、空key集合和未解析失败块给明确结果
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 15．未修改块保留原排版

- **来源／场景**：小改一个title时希望其他文献注释、空白和逗号完全保留；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/model.py)。
- **原版缺口**：Block有raw，默认writer重建已解析Entry，未提供write_preserving_source
- **交付及模块**：增加保留源模式：追踪修改字段，只对确实变更的块重写，其余输出原始片段；`bibtexparser/model.py:Block`, `bibtexparser/writer.py:write`, `bibtexparser/splitter.py:Splitter`。
- **兼容与实际依赖**：默认规范化writer不变；不能根据raw存在就误判字段未改，需可靠原值快照；步骤依赖：无。
- **正常验收**：改一条title后其他block字节保持原样，重解析改动值正确
- **异常／边界验收**：插入/删除字段、middleware改写、CRLF、失败块及原文无末尾换行均明确处理
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 16．原子文献文件写入

- **来源／场景**：保存本地文献库时写入失败不能留下截断文件；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/entrypoint.py)。
- **原版缺口**：write_file直接open目标w再write，无原子替换接口；当前先序列化减少部分失败但不保证磁盘写入原子性
- **交付及模块**：新增可选atomic写入，同目录临时文件写完后replace，保留明确的编码和权限策略；`bibtexparser/entrypoint.py:write_file`。
- **兼容与实际依赖**：原write_file默认行为可保留；文件对象不假装支持原子替换；只操作调用方路径；步骤依赖：无。
- **正常验收**：成功保存后文件重新解析一致，旧文件在替换前持续可读
- **异常／边界验收**：编码失败、写满、替换失败与权限不足保留原文件并清理本次临时文件
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 17．分块文献流解析

- **来源／场景**：处理大型.bib文件需逐条消费而不一次read全文件；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/entrypoint.py)。
- **原版缺口**：parse_file调用f.read，Splitter构造收完整字符串，无parse_stream
- **交付及模块**：新增分块解析入口，跨块保留引号/括号/注释状态并逐块生成Entry或失败块；`bibtexparser/entrypoint.py:parse_file`, `bibtexparser/splitter.py:Splitter`。
- **兼容与实际依赖**：完整parse_string结果保持；全库middleware在stream模式要明确延迟或不支持，不能静默漏依赖；步骤依赖：无。
- **正常验收**：任意字节/文本分块的文献与一次解析结果一致，首条可在EOF前消费
- **异常／边界验收**：跨块转义、@string前后引用、长单块上限、取消和末尾不完整记录有定位信息
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 18．字段跨度与统一诊断

- **来源／场景**：编辑器要定位同一行两个字段的解析错误；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/model.py)。
- **原版缺口**：Block/Field只有start_line，错误信息分散在ParsingFailedBlock及异常，缺少列/结束位置
- **交付及模块**：提供parse_with_diagnostics，记录字符跨度、阶段、稳定错误码和相关字段；`bibtexparser/model.py:ParsingFailedBlock`, `bibtexparser/model.py:Field`, `bibtexparser/splitter.py:Splitter`。
- **兼容与实际依赖**：保留容错parse_string返回类型；新增结果不把warnings与解析失败混为一谈；步骤依赖：无。
- **正常验收**：同一行缺逗号与重复字段得到各自准确跨度，可跳到对应原文
- **异常／边界验收**：Unicode字符列、CRLF、EOF缺括号及middleware无源位置明确标未知，不猜坐标
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 19．中间件变换过程报告

- **来源／场景**：研究导入链需知道哪一步改掉作者或丢出失败块；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/entrypoint.py)。
- **原版缺口**：parse/write stack可自定义且metadata存在，但无统一run_with_report入口或各阶段变化报告
- **交付及模块**：新增可选执行报告，保存每层耗时、块计数、变更字段和新增错误，并支持观察器；`bibtexparser/entrypoint.py:_build_parse_stack`, `bibtexparser/middlewares/middleware.py`。
- **兼容与实际依赖**：关闭报告时保持原性能/返回值；报告不保存全文副本或执行用户提供代码字符串；步骤依赖：无。
- **正常验收**：默认栈与作者拆分栈逐层报告可解释字段变化，结果与原流程一致
- **异常／边界验收**：middleware抛错、返回错误类型、取消与inplace/copy混合均记录实际阶段，失败不伪称完成
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。

## 20．书目库语义差异比较

- **来源／场景**：团队审查文献更改希望忽略缩进和字段顺序；[固定源码](https://github.com/sciunto-org/python-bibtexparser/blob/af329ca482b29691caff69cb2f8e6099670a105f/bibtexparser/library.py)。
- **原版缺口**：Library无diff，直接比较write_string会把纯排版当内容变化
- **交付及模块**：提供按citation key的语义diff，区分类型、字段、注释、宏和失败块变化，支持显式忽略规则；`bibtexparser/library.py`, `bibtexparser/model.py:Entry`, `bibtexparser/writer.py`。
- **兼容与实际依赖**：不自动合并；字符串宏是否先解析由调用方显式选择；字段原值与规范值分开；步骤依赖：无。
- **正常验收**：同语义不同排版无条目差异，真实author/year变更准确定位
- **异常／边界验收**：新增删除、改键、空值/缺值、多个同名失败块和组织作者列表保持确定顺序
- **原生回归**：`tests/test_entrypoint.py`, `tests/test_library.py`, `tests/test_model.py`, `tests/test_writer.py`, `tests/middleware_tests/test_interpolate.py`, `tests/middleware_tests/test_names.py`。
