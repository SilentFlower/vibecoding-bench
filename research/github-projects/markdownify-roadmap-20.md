# markdownify：二十步真实工程迭代路线

固定 [matthewwithanm/python-markdownify@bc98c9e134ec55b2853716ab859754f061cb7054](https://github.com/matthewwithanm/python-markdownify/tree/bc98c9e134ec55b2853716ab859754f061cb7054)，原生证据见 [单仓审查](./markdownify.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．CLI与API默认链接选项一致

- **来源／场景**：同一HTML在API和命令行转换希望得到同样默认链接；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/main.py)。
- **原版缺口**：main.py的store_true/store_false默认值覆盖API的autolinks/default_title；实跑默认CLI输出与API不同
- **交付及模块**：修正CLI默认/开关方向并明确提供成对启用禁用选项；`markdownify/main.py:main`, `markdownify/__init__.py:MarkdownConverter.DefaultOptions`。
- **兼容与实际依赖**：保持已显式选择的选项含义；对CLI旧默认变化提供说明，不拆为两个旗标迭代；步骤依赖：无。
- **正常验收**：默认CLI/API对同一链接得到相同Markdown，显式开关分别生效
- **异常／边界验收**：有title、文本不同于href、空链接及多个开关组合有一致退出与结果
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 02．连续定义术语保持共同定义关系

- **来源／场景**：词典的甲、乙共用一个dd；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_dt每个术语前加两换行，源码TODO明确连续dt应相邻；实跑两个术语被分开
- **交付及模块**：成组处理连续dt和后继dd，按声明Markdown定义列表方言输出；`markdownify/__init__.py:convert_dt`, `markdownify/__init__.py:convert_dd`。
- **兼容与实际依赖**：已有单术语定义保持；方言不支持定义列表时提供明确回退；步骤依赖：无。
- **正常验收**：两个dt相邻且共同dd缩进/标记正确，多个定义块边界保持
- **异常／边界验收**：连续dd、缺dd、空dt、术语含行内格式及嵌套块不串组
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 03．代码块围栏避让内容

- **来源／场景**：pre里的示例本身含三重反引号；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_pre固定三重围栏，实跑内容碰撞外层围栏；行内code已有动态定界，不重新计数
- **交付及模块**：为pre选择足够长的围栏并校验语言info，保留strip_pre合同；`markdownify/__init__.py:convert_pre`。
- **兼容与实际依赖**：普通内容输出保持；既有code_language_callback继续生效；不改行内代码算法；步骤依赖：无。
- **正常验收**：含三/四重反引号的pre最终仍为一个完整Markdown代码块
- **异常／边界验收**：空块、首尾换行、反引号语言标签、列表/引用中的代码均可还原文本
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 04．统一链接和图片Markdown序列化

- **来源／场景**：目标路径含空格/括号，图片alt含右方括号；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_a/img/video直接拼接目标或alt；实跑guide (v2).md及图]说明产生未完整转义结构
- **交付及模块**：集中实现目的地、标题和属性来源文字的序列化策略，复用到链接/图片/视频；`markdownify/__init__.py:convert_a`, `markdownify/__init__.py:convert_img`, `markdownify/__init__.py:convert_video`。
- **兼容与实际依赖**：不双重转义已处理普通文本；不下载目标；自动链接保留其明确条件；步骤依赖：无。
- **正常验收**：空格/成对及不成对括号路径、带右括号alt能被Markdown解析成原语义链接/图片
- **异常／边界验收**：反斜线、换行、单双引号、Unicode和空href不产生多余节点，所有调用点回归
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 05．有序列表编号完整语义

- **来源／场景**：HTML使用reversed、li value或负起始值；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_li只用isnumeric的start及前序li数量；reversed/value未实现，负start也回到1
- **交付及模块**：一次交付顺序/倒序计数、显式重设值和编号宽度缩进；`markdownify/__init__.py:convert_li`, `markdownify/__init__.py:convert_list`。
- **兼容与实际依赖**：普通start与无序bullets保持；这些是同一列表编号交付，不拆三个属性凑数；步骤依赖：无。
- **正常验收**：reversed start=3且第二项value=8得到3、8、7，后续缩进按数字宽度
- **异常／边界验收**：无start倒数、嵌套li不计父项、零/负编号、非法属性和空项都有明确结果
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 06．可选任务清单

- **来源／场景**：待办文档的checkbox状态需保留；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：input无专用converter，原版checked状态消失；自定义subclass可替代
- **交付及模块**：增加GFM任务列表选项，识别li内明确checkbox并保留状态；`markdownify/__init__.py:convert_li`, `markdownify/__init__.py:MarkdownConverter`。
- **兼容与实际依赖**：默认不额外产生任务标记；不推断运行时DOM状态；仅作用已声明checkbox；步骤依赖：无。
- **正常验收**：checked/unchecked输出对应任务标记且保持嵌套项内容
- **异常／边界验收**：多个控件、禁用状态、非checkbox、控件不在首位和空任务各有定义
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 07．纵向合并单元格展开

- **来源／场景**：目录表格有rowspan；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：td/th已有colspan占位，缺少rowspan网格；原版下行列数不足
- **交付及模块**：增加二维网格归一化，复用colspan并为rowspan补占位，提供无法表达时HTML回退；`markdownify/__init__.py:convert_td`, `markdownify/__init__.py:convert_tr`。
- **兼容与实际依赖**：不把已有colspan单独计数；普通矩形表保持；不静默丢合并文字；步骤依赖：无。
- **正常验收**：两行合并的首列得到稳定两列Markdown，文字仅按所选重复策略出现
- **异常／边界验收**：交叉跨度、超行、非法数值、多个thead/tbody及嵌套表明确回退/诊断
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 08．列对齐信息

- **来源／场景**：报表数值列align=right；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_tr分隔线统一---，不读取align或简单text-align
- **交付及模块**：增加列对齐策略，生成对应冒号分隔线并定义冲突优先级；`markdownify/__init__.py:convert_tr`。
- **兼容与实际依赖**：不执行完整CSS布局；无显式对齐保持原默认；步骤依赖：无。
- **正常验收**：左/中/右列输出各自Markdown对齐，单元格文字保持
- **异常／边界验收**：th与td冲突、未知CSS、空表、colspan和多表头有确定处理
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 09．参考式链接与统一编号

- **来源／场景**：同一指南URL在长文中重复，希望正文更清楚；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：链接只有inline/autolink，没有reference_links及去重引用定义
- **交付及模块**：增加参考链接模式，按规范化目的地/标题去重并稳定编号；`markdownify/__init__.py:convert_a`, `markdownify/__init__.py:convert_img`, `markdownify/__init__.py:convert__document_`。
- **兼容与实际依赖**：默认inline不变；同URL不同标题不擅自合并；图片与链接标签冲突可检验；步骤依赖：无。
- **正常验收**：多次同链接产生一个定义，首现顺序编号并可再次解析
- **异常／边界验收**：用户文字恰为引用标签、空链接、多段落和跨多次convert不泄漏引用状态
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 10．相对链接解析策略

- **来源／场景**：HTML从不同文档目录汇总为一本Markdown；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_a/img/video直接保留href/src，无base_url合同，传未知选项不会生效
- **交付及模块**：增加显式base URL和本地路径重写回调，统一处理所有资源目标；`markdownify/__init__.py:convert_a`, `markdownify/__init__.py:convert_img`, `markdownify/__init__.py:convert_video`。
- **兼容与实际依赖**：不访问网络；默认保留相对地址；片段和已有绝对地址各有明确规则；步骤依赖：无。
- **正常验收**：同一base下链接、图片、视频相对地址规范拼接且回调可观察
- **异常／边界验收**：根路径、点段、查询/片段、空base与不同协议不重复拼接或丢编码
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 11．选择DOM子树转换

- **来源／场景**：文档页面只转换article而略过nav；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：strip/convert按标签名控制格式转换且保留内容，不是CSS选择器提取
- **交付及模块**：利用已有BeautifulSoup DOM新增include/exclude selectors入口，定义重叠去重和顺序；`markdownify/__init__.py:convert_soup`, `markdownify/__init__.py:process_tag`。
- **兼容与实际依赖**：不把strip标签语义改成删除内容；默认整树转换保持；不新增抓取能力；步骤依赖：无。
- **正常验收**：选择article并排除其中nav后只得到正文，多个子树按原顺序
- **异常／边界验收**：重叠选择、无匹配、无效selector、被排除父项及传入已解析soup均有稳定行为
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 12．保留指定复杂标签为原HTML

- **来源／场景**：数学或SVG内容不能只保留拼接的文本；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：未知tag默认无converter，返回子文本；调用方可逐个subclass编写
- **交付及模块**：新增显式preserve_tags策略，完整输出指定DOM子树而不递归转其内部；`markdownify/__init__.py:process_tag`, `markdownify/__init__.py:get_conv_fn`。
- **兼容与实际依赖**：不是默认保留全部未知HTML；已有strip/convert优先关系明确；不声称保真浏览器布局；步骤依赖：无。
- **正常验收**：指定math/svg时原结构及属性保留，外部段落仍转Markdown
- **异常／边界验收**：嵌套保留标签、命名空间、注释、标签转义和冲突规则不双重处理
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 13．目录与稳定标题链接

- **来源／场景**：把多节文档转换后自动生成目录；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_hN只输出标题，无generate_toc或标题锚点冲突处理
- **交付及模块**：增加显式TOC模式，收集标题并使用选定渲染方言的slug/原id策略；`markdownify/__init__.py:convert_hN`, `markdownify/__init__.py:convert__document_`。
- **兼容与实际依赖**：默认不插目录；不假定各Markdown渲染器slug相同；生成位置可配置；步骤依赖：无。
- **正常验收**：多级标题目录层级及链接准确，重复标题生成稳定唯一目标
- **异常／边界验收**：Unicode、行内代码、原id、缺层级、同名标题和空标题有确定行为
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 14．标题层级迁移

- **来源／场景**：把网页章节并入一本书需整体下移一级；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：hN会截断到1..6，缺少heading_offset及超深层策略
- **交付及模块**：新增整体层级映射，支持offset/最小级别和超过6时的明确降级；`markdownify/__init__.py:convert_hN`。
- **兼容与实际依赖**：默认级别不变；Setext仅适用于迁移后的1/2级，不使用原级判断；步骤依赖：无。
- **正常验收**：h1/h2整体移为h2/h3并保留所选ATX/Setext风格
- **异常／边界验收**：负offset、超6、空标题、非标准h7和TOC配合有一致层级
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 15．语义脚注转换

- **来源／场景**：出版HTML用doc-noteref/doc-endnotes表示脚注；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：普通a和aside不维护脚注关系，没有专用收集与定义输出
- **交付及模块**：增加显式脚注模式，将已有role关系转为Markdown脚注，保留内容及多次引用；`markdownify/__init__.py:process_tag`, `markdownify/__init__.py:convert_a`, `markdownify/__init__.py:convert__document_`。
- **兼容与实际依赖**：不把普通数字链接猜为脚注；默认原转换保持；要求所选方言支持脚注；步骤依赖：无。
- **正常验收**：多次引用同一note只生成一个定义，嵌套段落缩进正确
- **异常／边界验收**：缺目标、重复id、仅定义无引用、反向导航与交叉引用给可复核回退
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 16．分层引号样式

- **来源／场景**：中文教材嵌套q需要“外层‘内层’”；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_q总加双引号，嵌套后无法区分层级；原版输出已保存
- **交付及模块**：新增quote_pairs与嵌套层级策略，可选保留HTML；`markdownify/__init__.py:convert_q`, `markdownify/__init__.py:process_tag`。
- **兼容与实际依赖**：默认旧双引号保持；不改普通文字中的引号；按DOM嵌套而非猜句法；步骤依赖：无。
- **正常验收**：两层q使用指定两组引号并正确闭合
- **异常／边界验收**：超过配置层数、空q、内联代码、引号内段落及不成对输入的DOM修复结果明确
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 17．选项及时校验

- **来源／场景**：误写选项或bullets空串不能到深处才出现零除等错误；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：options合并接受任意键，仅strip/convert互斥有校验；其他选项多在运行时隐式降级
- **交付及模块**：新增显式validate_options及可扩展选项schema，检查类型、枚举和组合；`markdownify/__init__.py:MarkdownConverter.__init__`, `markdownify/main.py:main`。
- **兼容与实际依赖**：自定义Options子类可声明扩展字段，不直接禁止现有合法扩展；默认兼容可用宽松模式；步骤依赖：无。
- **正常验收**：空bullets、未知heading_style、负wrap_width在严格入口得到具体选项错误
- **异常／边界验收**：None值、字符串/集合strip、未知kwargs、回调非callable和bs4_options类型均明示
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 18．一次转换的选项覆盖

- **来源／场景**：复用自定义converter时不同文档需要不同strip规则；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：实例options和convert_fn_cache可变；convert只接html，用户直接改options可能沿用旧分派缓存
- **交付及模块**：新增convert_with_options，以不变基础配置加本次覆盖，缓存按有效配置归属；`markdownify/__init__.py:MarkdownConverter.convert`, `markdownify/__init__.py:get_conv_fn_cached`。
- **兼容与实际依赖**：不改变现有subclass convert_*签名；原convert行为保持；每次覆盖不改基础实例；步骤依赖：无。
- **正常验收**：先保留strong再strip strong再保留，三个转换结果各符合本次选项
- **异常／边界验收**：嵌套调用、回调异常、共享实例并发及自定义Options字段不泄漏状态
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 19．DOM到Markdown来源映射

- **来源／场景**：校对转换结果时需找到原文节点；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/__init__.py)。
- **原版缺口**：convert_soup返回str，BeautifulSoup节点可被自定义converter访问但无输出范围对应表
- **交付及模块**：新增convert_with_map，记录输出段、DOM路径及可得的源行/列；`markdownify/__init__.py:process_element`, `markdownify/__init__.py:process_text`, `markdownify/__init__.py:convert_soup`。
- **兼容与实际依赖**：并非所有bs4 parser提供原字符位置，未知位置明确空值；不伪造字节保真；步骤依赖：无。
- **正常验收**：强调、链接和表格各输出段能关联正确DOM节点，拼接等于普通convert
- **异常／边界验收**：实体、合并空白、生成表头、回调替换和未提供源码坐标时均有明确来源种类
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。

## 20．CLI批量文档输出

- **来源／场景**：把一组本地HTML保留目录结构转换到新目录；[固定源码](https://github.com/matthewwithanm/python-markdownify/blob/bc98c9e134ec55b2853716ab859754f061cb7054/markdownify/main.py)。
- **原版缺口**：main只接一个输入并print，没有文件批次、输出路径和失败清单合同
- **交付及模块**：新增显式本地批量模式，输出编码、目录映射、冲突策略及逐项状态，完整写后发布单文件；`markdownify/main.py:main`, `markdownify/__init__.py:MarkdownConverter.convert`。
- **兼容与实际依赖**：单文件/stdin入口保持；不下载页面；不把部分批次成功称为全部成功；步骤依赖：无。
- **正常验收**：两份文档各写独立UTF8Markdown，目录及退出统计正确
- **异常／边界验收**：不可读输入、重名目标、单项转换错误、空批次和取消只影响本次结果，成功项可复核
- **原生回归**：`tests/test_basic.py`, `tests/test_args.py`, `tests/test_conversions.py`, `tests/test_custom_converter.py`, `tests/test_lists.py`, `tests/test_tables.py`, `tests/test_escaping.py`。
