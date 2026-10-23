# html2text：二十步真实工程迭代路线

固定 [Alir3z4/html2text@5cf85510a2498546d5b48ad1bf7d75b146aac591](https://github.com/Alir3z4/html2text/tree/5cf85510a2498546d5b48ad1bf7d75b146aac591)，原生证据见 [单仓审查](./html2text.md)。以下均为逐仓分析提出的本地工程增强提案，尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．行内代码动态定界符

- **来源／场景**：文档正文含 a`b 等反引号代码；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：handle_tag 总用一个反引号包 code，源码有 TODO；实测输出 `a`b`，不能完整表示代码文本
- **交付及模块**：对每段行内代码缓冲并选择大于内容最长反引号串的定界符，按 Markdown 空格规则包裹；`html2text/__init__.py:handle_tag`, `html2text/__init__.py:handle_data`。
- **兼容与实际依赖**：不含反引号的简单代码输出保持；kbd/tt 的同类代码定界一次交付，不拆步骤；步骤依赖：无。
- **正常验收**：a`b 和连续反引号经 Markdown 解析后保留完整代码内容
- **异常／边界验收**：首尾反引号、首尾空格、空代码及嵌套强调不会漏闭合或吃掉正文
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 02．代码块自适应围栏

- **来源／场景**：技术文档代码示例本身包含三个反引号；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：backquote_code_style 固定输出三个反引号；内容三个反引号与外层碰撞
- **交付及模块**：缓冲单个 pre 块，按内容选择反引号/波浪围栏及长度，保持块内文本；`html2text/__init__.py:handle_tag`, `html2text/__init__.py:o`。
- **兼容与实际依赖**：只有启用围栏时改变碰撞案例；原默认四空格缩进模式不变；步骤依赖：无。
- **正常验收**：包含三重和四重反引号的 pre 经 Markdown 解析仍为一个完整代码块
- **异常／边界验收**：列表/引用内 pre、空块、末尾无换行和内容含两类围栏都可恢复原文
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 03．代码语言标签保留

- **来源／场景**：文档导出含 class=language-python；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：现有围栏模式不读取 code 的 class，语言信息丢失；可自定义 tag_callback
- **交付及模块**：新增显式 preserve_code_language 选项，读取明确 language-/lang- 标记并附围栏 info；`html2text/__init__.py:handle_tag`, `html2text/config.py`。
- **兼容与实际依赖**：默认输出保持；只采纳明确语言标记，不从源码猜语言；非围栏模式不添加无效文字；步骤依赖：无。
- **正常验收**：Python 与 JavaScript 代码语言保留且正文不变
- **异常／边界验收**：多个冲突语言、空值、含空白/反引号的标签和 pre/code 双来源采用明确优先级
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 04．列表项显式编号

- **来源／场景**：导出列表中第二项以 li value=9 跳号；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：只读 ol start，li 分支每次 num+=1；实测 3、4、5，忽略 li value
- **交付及模块**：支持 li value 对当前有序列表计数重设，续项从重设值递增；`html2text/__init__.py:handle_tag`, `html2text/elements.py:ListElement`。
- **兼容与实际依赖**：无 value 行为保持；无序列表 value 不生效；不改变原生 ol start；步骤依赖：无。
- **正常验收**：start=3 第二项value=9 产生3、9、10，嵌套列表互不污染
- **异常／边界验收**：负数、零、无效值、重复 value 与超过9的缩进宽度均明确
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 05．反向编号有序列表

- **来源／场景**：HTML说明书使用 reversed 列表；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：ol reversed 属性未读取；原版仍递增，没有保留反向编号
- **交付及模块**：缓冲反向列表或预扫描当前列表项以求默认起点，支持 reversed 和显式 start/value；`html2text/__init__.py:handle_tag`, `html2text/elements.py:ListElement`。
- **兼容与实际依赖**：非 reversed 走原有流式路径；与第04步共享计数机制属于实际依赖；步骤依赖：04。
- **正常验收**：reversed start=3 的两项输出3、2；无start按当前层直接li数量倒数
- **异常／边界验收**：嵌套li不计入父层项数，value 重设后递减；未闭合列表有明确降级
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 06．任务列表复选状态

- **来源／场景**：离线待办 HTML 中含 checked input；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：input 未输出，checked 与 unchecked 任务均退化为普通项目文本
- **交付及模块**：增加可选 GitHub Markdown 任务列表模式，单项首个 checkbox 转为 [x]/[ ]；`html2text/__init__.py:handle_tag`, `html2text/config.py`。
- **兼容与实际依赖**：不宣称处理运行时DOM属性；默认纯文本转换保持；仅 list item 的明确 checkbox；步骤依赖：无。
- **正常验收**：两项任务分别保留已完成与未完成，文本和嵌套列表正确
- **异常／边界验收**：禁用checkbox、多个checkbox、非首位置input与普通radio明确保留文字或回退，不凭缺属性猜已完成
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 07．跨行跨列表格网格

- **来源／场景**：合并单元格的报表需可读且列数一致；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：table 分支按td直接插管道，不读取 colspan/rowspan；实测合并行列不齐
- **交付及模块**：一次交付 colspan/rowspan 网格归一化，可选重复文本、空占位或原HTML回退；`html2text/__init__.py:handle_tag`, `html2text/utils.py:pad_tables_in_text`。
- **兼容与实际依赖**：普通矩形表输出不变；不把单独测试维度拆成两步；合并语义不能在Markdown保真时明确回退；步骤依赖：无。
- **正常验收**：两列合并单元格与纵向合并均生成列数一致且文字不丢的结果
- **异常／边界验收**：非法跨度、交叉占位、表尾跨越、嵌套表格和空表有确定诊断/回退
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 08．表格标题独立呈现

- **来源／场景**：季度报表 caption 需要和表格建立可读关系；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：caption 无专用处理，文字与表格首行可能相连，语义丢失
- **交付及模块**：提供 caption 策略，将标题作为表格前后独立段落或明确保留HTML；`html2text/__init__.py:handle_tag`。
- **兼容与实际依赖**：默认选择需版本说明，旧表格无caption不变；不依赖第07步网格；步骤依赖：无。
- **正常验收**：标题在表前独立一段，内容首行仍是正确表头
- **异常／边界验收**：多个caption、内联强调、空caption及嵌套表格各自归属不混淆
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 09．表格列对齐

- **来源／场景**：数值列有 align=right 或 text-align:right；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：当前分隔行统一为 ---，未读取对齐信息
- **交付及模块**：增加简单表格列对齐分析，输出 :---、:---:、---: 的明确模式；`html2text/__init__.py:handle_tag`, `html2text/utils.py:pad_tables_in_text`。
- **兼容与实际依赖**：无显式对齐列仍用原默认；复杂CSS级联不在首版范围；步骤依赖：无。
- **正常验收**：左右居中的三列保留各自对齐，pad_tables 后语义保持
- **异常／边界验收**：冲突单元格、th优先规则、非法对齐、不同case和body覆盖策略稳定
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 10．折叠说明的语义转换

- **来源／场景**：手册用 details/summary 包装可展开说明；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：原版只串接文本，不保留 summary 与展开内容边界
- **交付及模块**：新增 details 策略：保留合法HTML，或转换成摘要段落加内容块；`html2text/__init__.py:handle_tag`, `html2text/config.py`。
- **兼容与实际依赖**：默认模式需明确兼容；不执行交互，不将是否open误认为应删除正文；步骤依赖：无。
- **正常验收**：summary 与正文转换后分离，保留HTML模式仍成对闭合
- **异常／边界验收**：嵌套details、缺summary、多个summary、空正文和跨块引用不丢字或错配
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 11．图片说明语义

- **来源／场景**：技术文档 figure 内含图片和 figcaption；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：figure/figcaption 无专用处理，图片与说明没有稳定的段落关系
- **交付及模块**：增加可选 figure 模式，保证图片与图说明成组并明确编号/强调策略；`html2text/__init__.py:handle_tag`。
- **兼容与实际依赖**：不自动替换图片alt为caption；现有 images_to_alt/ignore_images 仍各自生效；步骤依赖：无。
- **正常验收**：单图与说明分行且成组，说明含链接和强调可正常转为Markdown
- **异常／边界验收**：多图、缺图、空caption、嵌套figure和ignore_images时说明保留有断言
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 12．注音文字可读策略

- **来源／场景**：语言教材包含 ruby/rt/rp；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：原版直接连接所有文字，注音与兼容括号混入正文；无ruby选项
- **交付及模块**：一次提供 ruby 三种模式：仅主文、主文加统一括号注音、保留HTML；`html2text/__init__.py:handle_tag`。
- **兼容与实际依赖**：默认兼容旧输出；不做语言识别或发音生成；步骤依赖：无。
- **正常验收**：漢与kan 注音在不同模式各自精确输出，不重复rp括号
- **异常／边界验收**：多组rt、rtc、缺rp、空注音、嵌套行内格式与普通括号文字不误吞
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 13．本地媒体替代链接

- **来源／场景**：手册内 video/audio 含 source 和回退文字；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：原版只留回退文字，source 地址丢失；本库不加载媒体
- **交付及模块**：增加可选媒体策略，把明确源和poster转为有标签的普通链接清单；`html2text/__init__.py:handle_tag`。
- **兼容与实际依赖**：只转换已有HTML，不下载媒体；默认文本输出保持；source不应重复输出所有码率；步骤依赖：无。
- **正常验收**：视频与音频得到一个按规则选出的媒体链接和保留回退文字
- **异常／边界验收**：多源格式优先级、相对baseurl、无src、仅poster和不支持type不静默选择错误文件
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 14．内部章节链接与标题锚点

- **来源／场景**：文档转换后保留回到章节链接；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：skip_internal_links 默认丢内部href，关闭可留链接但h2 id未转换成可解析目标
- **交付及模块**：新增显式标题锚点策略，生成稳定Markdown标题slug或保留原id锚点，并重写已知片段链接；`html2text/__init__.py:handle_tag`, `html2text/utils.py:hn`。
- **兼容与实际依赖**：默认跳过内部链接的行为保持；不假定所有Markdown渲染器slug相同，必须选择具体模式；步骤依赖：无。
- **正常验收**：带id标题与其内部链接在选择的渲染配置下互相指向
- **异常／边界验收**：同名标题、Unicode、显式id与slug冲突、未知目标及跨文档链接不错误改写
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 15．HTML脚注转Markdown脚注

- **来源／场景**：出版导出使用 doc-noteref 和 doc-endnotes；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：原版无脚注身份处理，注号链接和正文单独串接，缺少规范定义关系
- **交付及模块**：增加 opt-in 脚注收集器，把明确role标记的引用和内容转为脚注引用/定义；`html2text/__init__.py:handle_tag`。
- **兼容与实际依赖**：不把普通数字上标或普通aside猜成脚注；默认输出保持；步骤依赖：无。
- **正常验收**：一条脚注被多次引用只生成一个定义，保留脚注内段落和链接
- **异常／边界验收**：缺目标、重复id、未引用定义、反向导航和嵌套脚注明确诊断/回退
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 16．响应式图片来源选择

- **来源／场景**：文档离线导出希望选择2x插图；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：img只读取src，不解析srcset/sizes或picture source；原版固定small.png
- **交付及模块**：提供显式像素密度或视口选项，解析合法srcset并按明确规则选择，不获取图片；`html2text/__init__.py:handle_tag`, `html2text/config.py`。
- **兼容与实际依赖**：无选项继续使用src；不能以HTML文本推断真实图片尺寸；首版不实现完整CSS布局；步骤依赖：无。
- **正常验收**：1x/2x候选在指定density下选对地址并按baseurl规范连接
- **异常／边界验收**：w/x混用、重复描述符、逗号URL、空集合与无匹配picture type有确定回退
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 17．转换结果的来源映射

- **来源／场景**：维护者需定位Markdown中一句话来自哪段HTML；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：handle 只返回str，tag_callback给事件但无输出跨度与输入坐标映射
- **交付及模块**：新增 handle_with_map，记录输出区间对应HTMLParser的来源位置及生成标记来源；`html2text/__init__.py:handle`, `html2text/__init__.py:outtextf`。
- **兼容与实际依赖**：普通handle 返回值与输出保持；生成的Markdown标记不伪造成原输入字符；步骤依赖：无。
- **正常验收**：段落、链接、实体与列表每个输出片段可定位对应HTML行列，拼接等于handle
- **异常／边界验收**：实体多码点、换行折叠、换行包装和生成引用定义的多对一映射显式可查询
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 18．有界分块文档转换

- **来源／场景**：长文档希望逐块输出而不累计整篇outtextlist；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：继承feed与out回调可接分块，但handle先整串feed后finish/optwrap，缺少明确handle_stream生命周期与刷新合同
- **交付及模块**：新增迭代式文本块接口，按完整段落刷新，保留跨块标签与引用状态并说明缓冲上限；`html2text/__init__.py:handle`, `html2text/__init__.py:finish`, `html2text/__init__.py:optwrap`。
- **兼容与实际依赖**：不把现有feed改名冒充新能力；默认字符串入口保持；需缓存整个表/代码块的选项明确声明；步骤依赖：无。
- **正常验收**：任意切分实体、标签、代码及链接的输入与一次handle得到同样最终文本
- **异常／边界验收**：空块、非字符串、取消、未闭合块、跨段落引用和超限大单块有确定清理与错误
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 19．明确校验的转换配置

- **来源／场景**：调用方误写 ignroe_links 时动态属性静默无效；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：配置为实例属性逐个赋值，构造函数只收out/baseurl/bodywidth，没有Options
- **交付及模块**：增加不可变Options及from_mapping校验入口，保持已有属性兼容层与CLI统一映射；`html2text/__init__.py:HTML2Text.__init__`, `html2text/config.py`, `html2text/cli.py:main`。
- **兼容与实际依赖**：现有直接属性赋值继续可用；新严格配置才拒绝未知字段；不引入全局配置突变；步骤依赖：无。
- **正常验收**：同一Options用于API和CLI产生一致Markdown，允许的组合有清晰默认
- **异常／边界验收**：拼错选项、负宽度、冲突images模式、single_line_break与width冲突均明确报错
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。

## 20．可见正文模式

- **来源／场景**：普通阅读导出不希望把template占位文字和明确hidden内容混进正文；[固定源码](https://github.com/Alir3z4/html2text/blob/5cf85510a2498546d5b48ad1bf7d75b146aac591/html2text/__init__.py)。
- **原版缺口**：quiet只处理head/style/script，template与hidden无专门规则；实测占位和隐藏说明均输出
- **交付及模块**：新增显式 visible_content 模式，跳过template与HTML hidden子树，并报告略去范围；`html2text/__init__.py:handle_tag`, `html2text/__init__.py:handle_data`。
- **兼容与实际依赖**：这是文档视图选择，不是安全清洗；默认保留旧文本，不解析任意CSS或推测脚本显示状态；步骤依赖：无。
- **正常验收**：明确hidden父级整棵子树与template内容不输出，普通正文完整保留
- **异常／边界验收**：嵌套隐藏、hidden=false的HTML布尔语义、未闭合标签及同名普通文字不会污染后续quiet计数
- **原生回归**：`test/test_html2text.py`, `test/test_memleak.py`, `test/test_newlines_on_multiple_calls.py`。
