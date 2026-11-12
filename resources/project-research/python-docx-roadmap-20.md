# python-docx：二十步真实工程迭代路线

固定 [python-openxml/python-docx@e45454602b53e8e572b179ccf1c91093ec9f4ed7](https://github.com/python-openxml/python-docx/tree/e45454602b53e8e572b179ccf1c91093ec9f4ed7)，详见[单仓审查](./python-docx.md)。共 20 步：17 项增强提案、3 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．空核心日期按缺失值处理（问题修复）

- 来源／场景：https://github.com/python-openxml/python-docx/issues/1622
- 原版现状：核心created元素存在但无text时_parse_W3CDTF切None，当前TypeError；缺整个元素原本返回None。
- 交付目标：空/无效日期安全返回None，保持现有对无效日期文本的约定。
- 影响模块：src/docx/oxml/coreprops.py:_datetime_of_element；opc/coreprops.py
- 兼容边界：不改变合法年月/日期/偏移解析；不以捕获所有异常掩盖内部问题。
- 正常验收：含空created/modified/lastPrinted的真实DOCX可打开并读取属性None。
- 异常／边界：空白、非法文本、缺元素、不同偏移与有效边界日期。
- 原生回归：tests/opc/parts/test_coreprops.py；核心属性oxml测试
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．写入 aware 核心时间先归一到 UTC（问题修复）

- 来源／场景：[src/docx/oxml/coreprops.py:_set_element_datetime；smoke实际往返](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/coreprops.py)
- 原版现状：2026-10-21T10:00+08:00直接strftime加Z后重读为10:00UTC，瞬间改变8小时。
- 交付目标：aware datetime先转UTC再写Z，明确naive继续按兼容政策处理。
- 影响模块：oxml/coreprops.py；opc/coreprops.py
- 兼容边界：保留原格式精度；不把无时区值擅自解释为宿主本地时区。
- 正常验收：10:00+08写后重读02:00UTC，与原输入表示同一瞬间。
- 异常／边界：负/非整小时偏移、跨日、DST aware实例、naive与微秒舍弃政策。
- 原生回归：tests/opc/parts/test_coreprops.py；文件往返断言
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．批注范围检查所属文档和顺序（问题修复）

- 来源／场景：[src/docx/document.py:add_comment；smoke跨文档文件复现](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/document.py)
- 原版现状：目的文档接收另一文档run后，comment写在目的包而范围标记写在另一包，留下悬挂引用。
- 交付目标：在创建comment前校验range runs属于当前主文档、顺序和可支持story。
- 影响模块：document.py:add_comment；text/run.py；comments/parts
- 兼容边界：正常单run/跨段范围保持；不把header/footer批注当已支持功能。
- 正常验收：跨文档输入受控拒绝，两个文档都不新增comments或range标记。
- 异常／边界：空序列、倒序run、不同table/story、不连续run契约及失败无副作用。
- 原生回归：tests/test_document.py/test_comments.py；features/doc-add-comment
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．超链接创建与修改的公共 API（增强提案）

- 来源／场景：src/docx/text/hyperlink.py只有只读属性；Paragraph无add_hyperlink；固定源码：[src/docx/text/hyperlink.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/text/hyperlink.py)。
- 原版现状：已能读取超链接和其runs，但新增/改地址需手写XML与relationship。
- 交付目标：提供add_hyperlink及address/fragment/text编辑，支持外部与书签内部跳转。
- 影响模块：text/paragraph.py/hyperlink.py；oxml/text/hyperlink；story关系
- 兼容边界：普通Run和已有链接读取保持；不从URL自动访问网络。
- 正常验收：创建含格式的外链，保存重开URL和文本保持，删除后清理未用关系。
- 异常／边界：空地址、带#片段、Unicode、重复关系、页眉/批注中的合法链接。
- 原生回归：tests/text/test_hyperlink.py；features/hlk-props
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．书签及内部交叉跳转（增强提案）

- 来源／场景：Paragraph/Run无bookmark代理；报告目录跳转场景；固定源码：[src/docx/text/paragraph.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/text/paragraph.py)、[src/docx/text/run.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/text/run.py)。
- 原版现状：w:bookmarkStart/End只能通过私有XML构造，ID/名称唯一性由用户自管。
- 交付目标：新增Bookmark集合与范围创建/删除/重命名，并联动显式内部超链接。
- 影响模块：新书签代理；paragraph/run；oxml与Document关系
- 兼容边界：不计算页码或生成Word渲染目录；已有未知书签无损保留。
- 正常验收：给标题创建唯一书签，正文链接跳到该名称，重开后range正确。
- 异常／边界：重复名/非法名、交叉range、跨story、重命名悬挂链接政策。
- 原生回归：段落/运行XML测试；独立ZIP书签ID校验
- 真实依赖：04

## 06．跨 Run 替换保留段落格式（增强提案）

- 来源／场景：Paragraph.text赋值会清除run结构；模板标记被Word拆段场景；固定源码：[src/docx/text/paragraph.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/text/paragraph.py)、[src/docx/text/run.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/text/run.py)。
- 原版现状：run级replace找不到跨run的${customer}，paragraph.text重写又丢所有字符格式。
- 交付目标：提供replace_text建立字符到run映射，只改匹配区域，明确新文本继承哪个格式。
- 影响模块：text/paragraph.py/run.py；hyperlink与内联内容映射
- 兼容边界：不改变现有text setter；首版不跨段落/表格单元格，不假装图形是字符。
- 正常验收：标记跨粗体/普通两个run也可替换，其他文字和格式不变。
- 异常／边界：重叠匹配、空替换、tab/break、超链接边界、批注/书签锚点。
- 原生回归：tests/text/test_paragraph.py/test_run.py；模板DOCX往返
- 真实依赖：03, 04, 05

## 07．结构化内容控件读写（增强提案）

- 来源／场景：Document/BlockItemContainer只公开Paragraph/Table；SDT合同模板场景；固定源码：[src/docx/document.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/document.py)、[src/docx/blkcntnr.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/blkcntnr.py)。
- 原版现状：现有SDT包内容可保留但无按tag/alias读取或填充的公共代理。
- 交付目标：新增ContentControl代理，首版plain text/rich text/checkbox，按显式tag定位填值。
- 影响模块：新增SDT模块；oxml；blkcntnr；document
- 兼容边界：不执行控件数据绑定外部源；未支持控件类型明确只读/拒绝修改。
- 正常验收：模板中Customer控件填值且保留周边格式和控件元数据。
- 异常／边界：重复tag、锁定控件、嵌套SDT、空内容、checkbox checked状态。
- 原生回归：blkcntnr/oxml模式；合成SDT文档独立解析
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．脚注和尾注正文接口（增强提案）

- 来源／场景：opc/constants.py有FOOTNOTES/ENDNOTES常量但无对应公开代理；固定源码：[src/docx/opc/constants.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/opc/constants.py)。
- 原版现状：关系常量存在不等于可创建/枚举/编辑脚注；用户需手工管理part与引用ID。
- 交付目标：提供Footnotes/Endnotes集合及run锚定，支持段落/链接与必要分隔项。
- 影响模块：新增note parts/代理；Run；Package part注册
- 兼容边界：不把comments当脚注；不自动引用外部文件，原未知note内容保留。
- 正常验收：正文插脚注后对应part、引用、content type齐全，重开可编辑。
- 异常／边界：保留ID、删除最后引用、同note多引用、注中表格/图片与损坏引用。
- 原生回归：tests/parts/test_story.py；OPC关系和新note fixtures
- 真实依赖：04

## 09．域与页码目录的结构化插入（增强提案）

- 来源／场景：Run公开API无field代理；PAGE/NUMPAGES/TOC场景；固定源码：[src/docx/text/run.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/text/run.py)。
- 原版现状：用户只能手写fldChar/instrText，容易缺begin/separate/end或错误缓存。
- 交付目标：新增Field代理与常见域创建，维护指令/缓存/dirty，支持页码和TOC指令。
- 影响模块：text/run；oxml/text；settings更新域标记
- 兼容边界：只写域不求值/排版，不承诺自动得到正确页码；默认不执行外链域。
- 正常验收：插PAGE/NUMPAGES与TOC域后XML平衡，缓存和更新标记可读回。
- 异常／边界：嵌套域、未知指令、含引号参数、跨run域、删除域保留缓存政策。
- 原生回归：run/oxml测试；实际DOCX域结构校验
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．按政策接受或拒绝修订（增强提案）

- 来源／场景：Document.paragraphs注明修订标记中的段落不包含；固定源码：[src/docx/document.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/document.py)、[src/docx/blkcntnr.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/blkcntnr.py)。
- 原版现状：原读取跳过部分w:ins/w:del，缺少对修订集合的公开管理。
- 交付目标：增加Revision集合与accept/reject，首版文本插入/删除及段落属性变更。
- 影响模块：document/blkcntnr；text代理；oxml修订元素
- 兼容边界：不启用任意宏；未支持move/table复杂修订应显式报告，不能静默丢失。
- 正常验收：文本插入接受留下新文，拒绝恢复原文；ID/作者/日期可枚举。
- 异常／边界：嵌套/重叠修订、评论/书签交叉、删除空段和未支持类型。
- 原生回归：tests/test_document.py；修订输入fixtures
- 真实依赖：03, 05, 06

## 11．文档自定义属性集合（增强提案）

- 来源／场景：Document.core_properties只覆盖Dublin Core字段；固定源码：[src/docx/opc/parts/coreprops.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/opc/parts/coreprops.py)。
- 原版现状：没有docProps/custom.xml类型化属性API，不能稳妥写模板版本/业务编号。
- 交付目标：提供custom_properties支持字符串/布尔/整数/浮点/时间，维护pid/fmtid/关系。
- 影响模块：新增customprops part/代理；OPC注册/content types
- 兼容边界：不改变core_properties；不把未知variant强转字符串，允许无损只读。
- 正常验收：写TemplateVersion/Approved并重开保持类型，更新不重复pid。
- 异常／边界：重名大小写、空名、无穷数、aware时间、删除最后属性部件清理。
- 原生回归：OPC coreprops模式；独立XML variant校验
- 真实依赖：02

## 12．编号列表的重启与多级配置（增强提案）

- 来源／场景：parts/numbering.py有底层part；Paragraph.style仅选预置List样式；固定源码：[src/docx/parts/numbering.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/parts/numbering.py)、[src/docx/oxml/numbering.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/numbering.py)。
- 原版现状：高层无法创建抽象编号/实例编号、指定起始值或多级格式，复杂列表需手写XML。
- 交付目标：新增ListDefinition与段落编号API，支持层级/起始/重启和显式文本格式。
- 影响模块：parts/numbering.py；oxml/numbering.py；ParagraphFormat
- 兼容边界：保留List Bullet/Number样式；不把实际显示编号写成普通正文。
- 正常验收：两份清单分别从1开始，二级a/b编号关系正确，重开可读。
- 异常／边界：重复numId、缺abstractNum、跨文档引用、特殊格式和删除列表定义。
- 原生回归：numbering part/oxml测试；实际列表文档
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．重复表头与行分页政策（增强提案）

- 来源／场景：table._Row只公开height/height_rule等；长报告分页场景；固定源码：[src/docx/oxml/table.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/table.py)。
- 原版现状：无法公共设置tblHeader/cantSplit等行分页属性，需要私有XML。
- 交付目标：Row增加repeat_header/allow_split_across_pages，维护正确trPr与三态继承。
- 影响模块：table.py:_Row；oxml/table.py
- 兼容边界：默认继承不变；只控制Word排版属性，不计算页面数量。
- 正常验收：首两行重复表头、数据行不跨页，重开属性和XML相符。
- 异常／边界：非首连续表头、None移除属性、合并行、嵌套表与空行。
- 原生回归：tests/test_table.py；tests/oxml/test_table.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．单元格边距边框与底纹配置（增强提案）

- 来源／场景：_Cell当前有width/vertical_alignment，缺少完整公共tcPr格式；固定源码：[src/docx/table.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/table.py)。
- 原版现状：表格设计需逐个手写tcMar/tcBorders/shd，单位和边枚举容易错。
- 交付目标：提供CellFormat统一边距、六边框、底纹主题/颜色及清除继承。
- 影响模块：table._Cell；oxml/table；共享长度/颜色
- 兼容边界：保留表样式继承；direct格式显式覆盖，未设置边不能被默认覆盖。
- 正常验收：报价表外粗内细、标题底纹和单元格留白保存重开正确。
- 异常／边界：None清除、主题色、零边距、合并单元格边界与非法长度/样式。
- 原生回归：test_table/oxml table；独立tcPr检查
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．表格插入删除保持合并网格（增强提案）

- 来源／场景：Table只有add_row/add_column；_Row.cells处理gridSpan/vMerge；固定源码：[src/docx/oxml/table.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/table.py)。
- 原版现状：中间插入/删除无API，直接移XML可能破坏跨行合并和省略网格。
- 交付目标：增加行列insert/delete，先校验受影响合并区域并按明确政策调整。
- 影响模块：table.py；oxml/table.py；网格辅助
- 兼容边界：首版遇不能可靠调整的复杂交叉合并明确拒绝，不静默拆表。
- 正常验收：普通表中间插行列后数据顺序正确，合并区外操作保持span。
- 异常／边界：vMerge起点删除、横跨删除列、gridBefore/After、最后行/列。
- 原生回归：tests/test_table.py及全部合并BDD场景
- 真实依赖：13, 14

## 16．浮动图片和环绕方式（增强提案）

- 来源／场景：InlineShapes/Run.add_picture仅inline；文档配图场景；固定源码：[src/docx/parts/story.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/parts/story.py)、[src/docx/oxml/shape.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/shape.py)。
- 原版现状：已能插行内图，但无anchor定位、相对页/段落、文字环绕公共接口。
- 交付目标：新增FloatingPicture，支持明确anchor位置和square/top-bottom环绕及关系复用。
- 影响模块：shape.py；parts/story.py；oxml/shape.py；Run
- 兼容边界：不改inline默认；首版限定图片，不声称任意Word绘图编辑器。
- 正常验收：图片相对页边定位、正文环绕属性完整，保存重开尺寸/关系不变。
- 异常／边界：页眉/单元格锚点、裁剪旋转、越界位置、层级behindDoc与图片数据失败。
- 原生回归：shape/story/oxml测试；实际anchor文档
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．合并文档时重映射相关部件（增强提案）

- 来源／场景：Document只追加内容原语；复制XML不会迁移图片/样式/编号；固定源码：[src/docx/document.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/document.py)。
- 原版现状：把另一个docx的段落直接deepcopy会产生丢图/错样式/编号ID冲突，没有受控导入入口。
- 交付目标：insert_document复制支持的段落/表及图片/超链接，重映射样式/编号/书签/批注关系。
- 影响模块：document/Package；styles/numbering/comments；OPC parts
- 兼容边界：首版列清支持part，未知嵌入/修订明确拒绝；不共享两个package的可变parts。
- 正常验收：两份都含图片和同名编号的文档合并后每项关系闭合、内容各自正确。
- 异常／边界：名字冲突、相同图片去重、节分隔、批注ID、循环关系及失败原子性。
- 原生回归：OPC/Document/numbering样式原生回归
- 真实依赖：03, 04, 05, 11, 12, 15, 16

## 18．按顺序遍历全部 story 内容（增强提案）

- 来源／场景：Document/Section/Paragraph已有各级iter_inner_content；固定源码：[src/docx/document.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/document.py)、[src/docx/blkcntnr.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/blkcntnr.py)。
- 原版现状：单容器顺序遍历已有，但全文索引仍需手写页眉页脚/表格递归/脚注与链接组合。
- 交付目标：提供walk_content输出story/路径/容器及内联事件，显式选择重复链接story与嵌套表政策。
- 影响模块：document/section/blkcntnr；text；新增walker
- 兼容边界：不重复计算已有iter_inner_content功能；默认不展开隐藏修订内容，不能声称阅读顺序等于视觉布局。
- 正常验收：正文表格、页眉、脚注及超链接文字均有来源路径且顺序符合各story XML。
- 异常／边界：共享header不重复、嵌套表、空段、修订和图形对象占位政策。
- 原生回归：blkcntnr/paragraph/section测试；全文索引场景
- 真实依赖：08, 10

## 19．图片替代文本与标题的可访问接口（增强提案）

- 来源／场景：InlineShape只有type/width/height；图片辅助阅读场景；固定源码：[src/docx/oxml/shape.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/shape.py)。
- 原版现状：docPr可含descr/title但现有公开代理不能稳定读取/修改。
- 交付目标：InlineShape/FloatingPicture暴露alt_text/title与decorative政策，正确写docPr/扩展。
- 影响模块：shape.py；oxml/shape.py
- 兼容边界：默认不从文件名猜描述；decorative和有意义描述冲突需明确。
- 正常验收：产品图写替代文本，重开与独立XML一致，批量审查能找缺描述图。
- 异常／边界：Unicode/空值、重复docPr ID、页眉图片及未知扩展保留。
- 原生回归：tests/test_shape.py；story图片BDD
- 真实依赖：16

## 20．节的多栏版式（增强提案）

- 来源／场景：Section有页边距/方向/页眉页脚但无columns公共接口；固定源码：[src/docx/oxml/section.py](https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/src/docx/oxml/section.py)。
- 原版现状：同一文档报告正文两栏与附录一栏需手写w:cols。
- 交付目标：增加Section.columns支持等宽栏数/栏距/分隔线及显式不等宽配置。
- 影响模块：section.py；oxml/section.py
- 兼容边界：默认单栏不变；不计算排版或自动插分页，节start_type沿现有API。
- 正常验收：正文两栏且附录新节一栏，保存重开栏宽/间距正确。
- 异常／边界：栏数0、可用页宽、横向页面、分栏符、不等宽总和越界及继承节。
- 原生回归：tests/test_section.py/oxml section；全部1609单测+650BDD
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
