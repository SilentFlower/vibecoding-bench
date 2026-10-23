# XlsxWriter：二十步真实工程迭代路线

固定 [jmcnamara/XlsxWriter@5d4606d89a955226d2d0825a0f44309043ae7251](https://github.com/jmcnamara/XlsxWriter/tree/5d4606d89a955226d2d0825a0f44309043ae7251)，详见[单仓审查](./xlsxwriter.md)。共 20 步：16 项增强提案、4 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．关闭字符串公式转换也覆盖数组公式（问题修复）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1212
- 原版现状：strings_to_formulas=False仍让{=1+1}进入_formula；smoke的A1生成<f>而非文本。
- 交付目标：同一开关同时约束普通=与{=}自动识别，显式write_formula仍可写公式。
- 影响模块：worksheet.py:_write_token_as_string；write
- 兼容边界：默认True行为兼容；显式公式接口不受此自动识别选项限制。
- 正常验收：关闭后两种公式状字符串都是文本，开启后按原语义生成公式。
- 异常／边界：空串、花括号普通文本、write_row/column、字符串数字/URL开关组合。
- 原生回归：test/worksheet；comparison数组公式fixtures
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．条件格式文本正确转义双引号（问题修复）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1206
- 原版现状：文本条件值special"sale被直接插入SEARCH/LEFT/RIGHT公式，生成错误引号。
- 交付目标：在Excel公式字符串字面量中将双引号成对转义，text属性仍保留原值。
- 影响模块：worksheet.py:conditional_format text分支
- 兼容边界：XML转义不能替代公式字符串转义；现有不含引号文本输出保持。
- 正常验收：containing/not containing/begin/end四种条件中的引号均生成合法公式文本。
- 异常／边界：连续引号、空文本、中文、XML元字符与通配符的已有语义不改变。
- 原生回归：test/worksheet条件格式；comparison条件格式fixtures
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．超长超链接提示在赋值后校验（问题修复）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1202
- 原版现状：Url构造时_tip为空，write_url/from_options/setter随后写入而未检查；当前256字符tooltip进入XML。
- 交付目标：集中在最终tip赋值与序列化前校验255限制，保持各入口一致。
- 影响模块：url.py:tip/from_options；worksheet._write_url；对象链接入口
- 兼容边界：不悄悄截断；保持错误/返回码风格并明确边界，不改变URL主体限制。
- 正常验收：255提示成功，256被清晰拒绝且不创建无效hyperlink。
- 异常／边界：Url实例、图片/文本框链接、None/空tip、Unicode与重复赋值。
- 原生回归：test/url；test/worksheet超链接；comparison链接文件
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．定义名和表名限制在255字符内（问题修复）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1204
- 原版现状：define_name及add_table当前均接受256字符名并写入OOXML；已有语法检查却漏长度。
- 交付目标：统一检查去掉局部sheet前缀后的定义名及table名称长度，失败不留下部分注册。
- 影响模块：workbook.py:define_name；worksheet.add_table；table.py
- 兼容边界：255以内保持；局部名称按实际名称计数，现有警告/返回码与大小写唯一规则一致。
- 正常验收：255成功、256明确失败，其他表/名字仍可继续创建。
- 异常／边界：Unicode、sheet!local、重名、自动TableN、范围重叠失败不能污染table_cells。
- 原生回归：test/workbook/test_define_name；test/worksheet/test_add_table
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．从既有格式复制并覆盖属性（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/81
- 原版现状：Format可原地修改且影响所有引用单元格，无公共完整copy入口，调用方需保留原属性dict。
- 交付目标：Workbook.copy_format(source,overrides)返回独立格式，重用合法样式归并。
- 影响模块：workbook.py:add_format；format.py属性与索引
- 兼容边界：复制语义不复制跨workbook内部索引；修改新格式不回写源。
- 正常验收：标题格式复制加边框，原标题字体不变，最终styles.xml引用正确。
- 异常／边界：颜色主题对象、num_format、保护、空overrides和跨workbook源需明确支持/拒绝。
- 原生回归：test/format；test/styles；comparison格式
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．工作簿主题与默认字体公开配置（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1163
- 原版现状：Format有theme索引与单格式字体，但缺少完整主题/默认字体的稳定workbook API。
- 交付目标：增加显式theme输入与默认字体参数，同步theme/styles及列宽度量基准。
- 影响模块：workbook.py；theme.py；format.py；worksheet列宽
- 兼容边界：默认Calibri主题保持；不把单个Format.set_theme索引误当完整主题支持。
- 正常验收：设置企业色板和字体后，未显式格式单元格/图表主题引用一致。
- 异常／边界：无效theme XML、缺必需色项、显式字体优先、只读输入与字体缺失退化。
- 原生回归：test/theme/test/styles；comparison主题文件
- 真实依赖：05

## 07．常量内存模式下增量自动列宽（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1125
- 原版现状：autofit在constant_memory直接警告返回，写过行已丢弃，无法事后扫描。
- 交付目标：写单元格时维护每列宽度摘要，流结束仍可autofit且不保存全部单元格。
- 影响模块：worksheet.py:写入分派/_write_single_row/autofit
- 兼容边界：默认普通模式不变；明确公式无缓存时估算、合并单元格和最大宽度规则。
- 正常验收：十万行流式输出仍能按最长文本设置列宽，摘要大小只随列数变化。
- 异常／边界：换行/富文本/日期/数字、手工set_column优先、空列和写入失败不污染摘要。
- 原生回归：test/worksheet autofit/constant_memory；comparison列宽
- 真实依赖：06

## 08．气泡图系列与大小维度（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1099
- 原版现状：add_chart类型表没有bubble，scatter仅有x/y不能表达第三个size维度。
- 交付目标：新增Bubble图类型，支持x/y/size引用、气泡比例与负值显示政策。
- 影响模块：workbook.add_chart；新增chart_bubble.py；chart.py缓存
- 兼容边界：不把scatter点尺寸当等价功能；保持现有图表类型分派。
- 正常验收：销售额/增长/规模三列生成c:bubbleChart及对应size缓存。
- 异常／边界：长度不等、空/非数值size、组合图限制、负size和无缓存源。
- 原生回归：test/chart_*模式；新增bubble比较fixture
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．表筛选器切片器对象（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/918
- 原版现状：有table/autofilter但无slicer对象、缓存与相关关系部件。
- 交付目标：首版支持普通table单列切片器，生成缓存、绘图与内容类型关系。
- 影响模块：table.py；worksheet.py；packager/contenttypes/relationships；新增slicer
- 兼容边界：不承诺PivotTable切片器；已有table筛选保持，禁止无表源。
- 正常验收：Region表列切片器写入有效部件且指向正确table/column。
- 异常／边界：重名、未知列、多个sheet共享缓存、隐藏值与不支持版本显式说明。
- 原生回归：comparison表/绘图；新增标准OOXML参照fixture
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．批注中的分段富文本（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/634
- 原版现状：write_comment接收单字符串，options统一字体，不支持每段粗体/颜色。
- 交付目标：新增rich comment runs，保持作者/可见性/框位置并输出多段rPr。
- 影响模块：worksheet.write_comment；comments.py；format字体验证
- 兼容边界：普通字符串仍按原API；不复用单元格样式索引到comment XML。
- 正常验收：批注标题粗体红色、正文普通，独立XML解析可看到各run样式。
- 异常／边界：空run、非法格式、总字符限制、Unicode换行及批注默认作者。
- 原生回归：test/comments；comparison批注文件
- 真实依赖：05

## 11．首页独立页眉与页脚（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/454
- 原版现状：set_header/footer目前输出普通页眉页脚，未提供differentFirst及firstHeader/firstFooter。
- 交付目标：支持首页/奇偶页文本与图片配置，按OOXML生成对应节点和图片关系。
- 影响模块：worksheet.set_header/set_footer/_write_header_footer；VML关系
- 兼容边界：默认普通页保持；不能只写differentFirst标志却漏首页内容/图片关系。
- 正常验收：封面页空页眉，后续页公司标题；首页页脚可单独编号。
- 异常／边界：255限制、同时奇偶页、图片缺失、chartsheet打印与空首页内容。
- 原生回归：test/worksheet header/footer；comparison打印文件
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．图表分类轴标签距离（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1182
- 原版现状：轴配置含多种标签属性，但没有公开label offset来控制标签距轴距离。
- 交付目标：为适用分类轴增加label_offset并写c:lblOffset，校验Excel范围。
- 影响模块：chart.py:set_x_axis/_write_cat_axis；各chart派生
- 兼容边界：默认原输出不变；数值轴不支持时明确拒绝/警告，不能静默丢选项。
- 正常验收：0/100/最大合法偏移生成对应轴节点，主副轴分别生效。
- 异常／边界：非法类型/越界、date轴、反向轴、组合图与无labels状态。
- 原生回归：test/chart轴；comparison轴配置
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．组合图中的散点数值轴配置（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/415
- 原版现状：现有combine存在，但混合scatter需要两条数值轴时的限制影响科学图。
- 交付目标：明确支持的column/line+scatter组合结构，独立数值x轴与主副轴ID/交叉关系。
- 影响模块：chart.py:combine；chart_scatter.py；轴写入
- 兼容边界：保留已有组合；只支持已验证组合，不泛化任意图表混合。
- 正常验收：分类柱形与数值散点共图，四轴关系可解析且散点按真实x值排列。
- 异常／边界：轴ID冲突、反向/对数轴、日期、气泡组合不在首版与空series。
- 原生回归：comparison组合图；chart_scatter/column测试
- 真实依赖：08, 12

## 14．显式加入自定义功能区 XML（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1086
- 原版现状：支持VBA工程但无public customUI部件输入与关系打包接口。
- 交付目标：增加add_custom_ui接收显式XML与图片映射，写customUI关系/内容类型，验证所需部件。
- 影响模块：workbook.py；packager.py；contenttypes/relationships
- 兼容边界：只生成包不执行宏/回调，不自动读取任意外部路径；无customUI时包保持原样。
- 正常验收：预置功能区按钮XML和图标成为对应部件，既有vbaProject仍可共存。
- 异常／边界：坏XML、重复关系ID、图片缺失、不带宏时回调提示和只读流。
- 原生回归：comparison VBA/图片；独立ZIP关系闭合校验
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．按显示值与字体估算自动列宽（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1183
- 原版现状：autofit为模拟计算，数字按原值字符数，日期/格式/字体会使实际显示宽度不同。
- 交付目标：增加显式display_width回调和已支持数字/日期格式估算，记录无法可靠估算的场景。
- 影响模块：worksheet.autofit；utility字符宽度；Format
- 兼容边界：默认近似算法兼容；不承诺完整Excel渲染器或所有自定义格式。
- 正常验收：千分位/百分号/日期按显示文本估宽，业务回调可覆盖未知格式。
- 异常／边界：CJK/emoji、科学记数、换行、字体大小、条件格式及stream摘要一致。
- 原生回归：autofit测试；格式显示参照fixture
- 真实依赖：06, 07

## 16．写入失败可选择异常政策（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/1100
- 原版现状：write_*用负整数混合warnings，调用方忽略返回值会漏掉越界或文本截断。
- 交付目标：增加error_policy=return/raise及有名称的写入状态，异常带sheet/cell/操作。
- 影响模块：worksheet写入口；exceptions.py；workbook options
- 兼容边界：默认return兼容；不把合法空单元格当失败，异常模式不重复警告。
- 正常验收：越界、长字符串和非法表参数在raise模式可捕获，正常写返回原成功。
- 异常／边界：write_row多项部分成功政策、用户write_handler、重复range及关闭后写入。
- 原生回归：test/worksheet写入分派及错误边界
- 真实依赖：01, 03, 04

## 17．关闭前输出结构化预检报告（增强提案）

- 来源／场景：workbook.close/packager；集中审阅多sheet生成问题场景；固定源码：[xlsxwriter/workbook.py](https://github.com/jmcnamara/XlsxWriter/blob/5d4606d89a955226d2d0825a0f44309043ae7251/xlsxwriter/workbook.py)、[xlsxwriter/packager.py](https://github.com/jmcnamara/XlsxWriter/blob/5d4606d89a955226d2d0825a0f44309043ae7251/xlsxwriter/packager.py)。
- 原版现状：警告分散，关闭时错误未形成可供调用方查看的sheet/对象级报告。
- 交付目标：增加validate报告命名、范围、表/图/链接关系与已知限制，strict close可在打包前失败。
- 影响模块：workbook/worksheet/chart预检；packager；诊断类型
- 兼容边界：默认不增加完整扫描；不是保证Excel所有版本都能渲染，也不求值公式。
- 正常验收：同时有坏chart源/悬挂名称能在一个报告中定位并阻止写出。
- 异常／边界：未知源引用、对象重复使用、预算、constant_memory无法回看的信息提前采集。
- 原生回归：comparison结构校验；所有原生测试
- 真实依赖：04, 16

## 18．同一工作簿内复制基础工作表（增强提案）

- 来源／场景：Workbook仅add_worksheet/get_worksheet_by_name；重复月报场景；固定源码：[xlsxwriter/workbook.py](https://github.com/jmcnamara/XlsxWriter/blob/5d4606d89a955226d2d0825a0f44309043ae7251/xlsxwriter/workbook.py)。
- 原版现状：没有公开clone_worksheet，复制Python私有属性容易共享可变对象或错误关系。
- 交付目标：首版复制单元格/格式/行列/筛选/冻结/打印配置到新sheet，复杂对象明确拒绝或单独映射。
- 影响模块：workbook.py；worksheet基础数据；sharedstrings/format引用
- 兼容边界：仅同工作簿普通内存模式；不变成读取现有XLSX模板的工具，不承诺图表对象盲复制。
- 正常验收：1月表复制为2月表后改数据互不影响，公共Format合法共享。
- 异常／边界：重名/非法sheet名、公式相对引用政策、合并范围、已刷盘行和复杂对象。
- 原生回归：test/workbook/worksheet；新增复制比较文件
- 真实依赖：05, 17

## 19．批注附带图片部件（增强提案）

- 来源／场景：https://github.com/jmcnamara/XlsxWriter/issues/823
- 原版现状：普通批注支持文本/框样式，无法把商品图片作为批注背景/附图打包。
- 交付目标：显式comment image输入，复用图片解析并生成VML相关图片关系与尺寸。
- 影响模块：comments.py；vml.py；worksheet.write_comment；packager
- 兼容边界：不把worksheet.insert_image当批注图片；图片仅显式传入，不进行URL下载。
- 正常验收：商品批注含缩略图，ZIP内图片和VML关系正确闭合。
- 异常／边界：不支持图像格式、损坏流、缩放/透明度、与rich comment共存及重复图片去重。
- 原生回归：comparison image/comment/VML；独立图片尺寸解析
- 真实依赖：10

## 20．动态数组公式可携带完整缓存网格（增强提案）

- 来源／场景：worksheet.py:write_dynamic_array_formula/_write_array_formula；固定源码：[xlsxwriter/worksheet.py](https://github.com/jmcnamara/XlsxWriter/blob/5d4606d89a955226d2d0825a0f44309043ae7251/xlsxwriter/worksheet.py)。
- 原版现状：现有动态数组和单个value缓存已存在，但非计算型预览器拿不到整个spill区域的显式缓存。
- 交付目标：允许提供形状匹配的cached_values网格，写锚点公式和对应从属缓存单元格。
- 影响模块：worksheet公式/数组cell模型；metadata；XML写入
- 兼容边界：不实现Excel公式求值；缓存由调用方提供，默认仍原锚点缓存与重算标记。
- 正常验收：2x2动态数组预览有四个缓存值，Excel重算元数据仍正确。
- 异常／边界：形状不符、类型/错误值、spill区域冲突、constant_memory顺序和空缓存。
- 原生回归：test/worksheet array formula；comparison动态数组；完整1787回归
- 真实依赖：16, 17

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
