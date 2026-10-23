# Webcolors：二十步真实工程迭代路线

固定[ubernostrum/webcolors@6c8da6832eb4ae2591a1883a0d1371263d6cd4db](https://github.com/ubernostrum/webcolors/tree/6c8da6832eb4ae2591a1883a0d1371263d6cd4db)，来源和原生基线见[单仓研究](./webcolors.md)。以下4项已复现缺陷的修复提案、16项本地增强均未实施；每项包含实现、测试、文档及失败修复，不拆分计数。FAQ的设计取舍如实保留，扩展不代表上游路线。

## 01．CSS4名称双向转换与公开枚举一致

- 来源/现状：读取[src/webcolors/_definitions.py](https://github.com/ubernostrum/webcolors/blob/6c8da6832eb4ae2591a1883a0d1371263d6cd4db/src/webcolors/_definitions.py)。CSS4表已声明rebeccapurple，反向可返回该名；正向注册却误指CSS3表，names(css4)漏项，顶层未导出CSS4。
- 交付：统一CSS4名称、公开常量及默认spec合同，修复正向/反向/枚举闭环，并核对_html5.py的独立名称表：现行WHATWG命名颜色包含rebeccapurple，原版旧式入口却算出(14,202,0)。本步一并让该名称返回(102,51,153)，更新同一交付中的参数说明。模块为_definitions.py、_conversion.py、_html5.py、__init__.py。
- 兼容：显式CSS3仍不接受rebeccapurple；默认spec选择需按已有转换默认与版本说明确定，不能悄悄让旧规范增加颜色。
- 正常验收：css4枚举包含新名，name→hex→name为rebeccapurple/#663399；CSS4可由顶层导入，现行规则下HTML旧式名称入口得到同一RGB。
- 边界验收：所有五种spec、未知spec、大小写、gray/grey和aqua/cyan别名均保持各自约定。回归tests/test_conversion.py、tests/test_conformance.py；依赖无。

## 02．HTML旧颜色解析只移除ASCII空白

- 来源/现状：[WHATWG旧颜色规则](https://html.spec.whatwg.org/multipage/common-microsyntaxes.html#rules-for-parsing-a-legacy-color-value)限定ASCII空白，_html5.py使用str.strip额外移除NBSP。实跑NBSP+red+NBSP返回红色，按剩余字符规则应得到(0,237,0)。
- 交付：在html5_parse_legacy_color使用精确的ASCII空白集合，保留非ASCII字符进入已有宽容算法；不重写整个解析器。
- 兼容：普通空格/TAB/LF/CR/FF仍可修剪；不能把旧式算法变成严格CSS解析。
- 正常验收：NBSP样本为#00ed00，ASCII空白包围red仍为#ff0000。
- 边界验收：仅空白、不同Unicode空白、透明关键字、非BMP和128字符截断按所选规则处理；既有普通名称保持，额外CSS4名称由01统一修复。本步空白处理可独立验收，不因名称集合残余缺口误称全规范通过。回归tests/test_html5.py；依赖无。

## 03．Hex规范化完整匹配输入

- 来源/现状：_definitions.py的正则使用$，normalize_hex收到#abc后跟单个LF时实际接受该值；[格式约定](https://github.com/ubernostrum/webcolors/blob/6c8da6832eb4ae2591a1883a0d1371263d6cd4db/docs/conventions.rst)只允许#后精确3或6个十六进制字符。
- 交付：让_normalization.py与_HEX_COLOR_RE完整匹配整个输入，所有通过normalize_hex的转换保持相同格式判断。
- 兼容：大小写与三位展开保持；允许修剪的HTML旧式入口继续拥有独立规则，不把两种合同混合。
- 正常验收：#AbC变#aabbcc，末尾LF的三/六位值明确拒绝。
- 边界验收：首尾空白、CRLF、额外字符、Unicode近似字母、空串和非法长度不被截断后接受。回归tests/test_normalization.py、tests/test_conversion.py；依赖无。

## 04．十进制百分比负零规范化

- 来源/现状：conventions.rst承诺负零规范化；_normalize_percent_rgb处理'-0%'为'0%'，但'-0.0%'仍保留负号，数值转换为RGB则已正确为0。
- 交付：在_normalization.py对可接受的十进制零统一输出无负号的零百分比，保留非零值与原裁剪范围。
- 兼容：修复字符串规范化，不声称原版黑色数值错误；不借机重写全部精度策略。
- 正常验收：-0%、-0.0%、-00.00%均得到规定的零表示，转换结果仍为0。
- 边界验收：微小负非零仍按裁剪处理，正零、整数/小数百分比及非法数值各走既有或明确错误规则。回归tests/test_normalization.py、tests/test_conversion.py；依赖无。

## 05．保留透明度的RGBA十六进制往返

- 来源/现状：FAQ明确当前不处理alpha；_types.py只有三通道类型，hex_to_rgb拒绝#33669980。主题资产需要在转换时保留透明度，当前可手工拆分alpha。
- 交付：新增明确RGBA类型及四/八位hex解析、序列化和不透明RGB适配，声明alpha为0..1或独立8位的表示规则。扩展_types.py、_normalization.py、_conversion.py及顶层导出。
- 兼容：原RGB函数不静默丢alpha，原HTML5简单颜色仍严格三通道；透明转不透明必须显式给策略或背景。
- 正常验收：#3698展开后颜色与alpha逐通道保持，八位值往返无损。
- 边界验收：alpha=0/1、颜色隐藏在透明像素中、非法长度、越界与取整边界明确；回归tests/test_conversion.py、tests/test_html5.py并新增RGBA集合。依赖无。

## 06．CSS rgb与rgba函数文本转换

- 来源/现状：_conversion.py接受RGB tuple而非完整CSS函数文本，现有name_to_rgb按名称查找，不能解析rgb(10 20 30 / 50%)；公开入口和FAQ均无文本parser。
- 交付：新增rgb()/rgba()解析与序列化，支持声明版本的逗号语法和空格/斜线语法、数值/百分比通道，复用RGBA结果类型。新增函数文本模块并使用_conversion.py、_normalization.py。
- 兼容：不改变名称函数为任意CSS解释器，不求值var()/calc()或整份样式表；支持的语法范围显式列出。
- 正常验收：两种语法得到相同颜色，百分比alpha保存，序列化再解析语义相同。
- 边界验收：混合分隔符、缺通道、none支持政策、指数/非有限值及越界裁剪按冻结规范处理。回归tests/test_conversion.py、tests/test_normalization.py；功能依赖05。

## 07．HSL与HSLA完整格式适配

- 来源/现状：FAQ建议调用者自行用colorsys转换；现有公开函数没有HSL文本、角度单位及alpha合同。网页主题编辑器需要直接处理hsl()。
- 交付：新增HSL类型、HSL/RGB双向转换及hsl()/hsla()文本往返，优先复用标准库colorsys并正确适配其HLS参数顺序。扩展_types.py、_conversion.py及新增格式模块。
- 兼容：标为本地增强；旧RGB默认保持，色相单位与无色彩时的色相表示显式；不声称原版无法经外部代码完成。
- 正常验收：hsl(120 100% 50%)为绿色，alpha及deg/turn等声明单位等价。
- 边界验收：绕回角度、灰阶、饱和/亮度边界、负色相及取整误差范围明确；回归tests/test_conversion.py、tests/test_normalization.py。标准库colorsys，无新外部依赖；功能依赖05。

## 08．HWB颜色格式互通

- 来源/现状：公开入口不含HWB，设计工具导出的hwb()目前须外部转换；当前HTML旧式函数不是CSS函数parser。
- 交付：增加HWB/RGB双向转换及hwb()文本往返，明确whiteness+blackness大于1时的规范处理，保存alpha。扩展_types.py、_conversion.py及格式模块。
- 兼容：与HSL分别提供独立模型；按固定[CSS Color 4版本](https://www.w3.org/TR/2026/CRD-css-color-4-20261020/)实现支持子集，不宣称支持全部CSS4。
- 正常验收：hwb(120 0% 0%)为绿色，白/黑份量及alpha往返满足容差。
- 边界验收：灰阶、白黑总和超限、色相单位、缺失分量与非有限值明确；回归tests/test_conversion.py、tests/test_normalization.py。默认标准库；功能依赖05。

## 09．可选择精度的百分比转换

- 来源/现状：rgb_to_rgb_percent有128→50%、64→25%的兼容特例及两位小数，FAQ明确这是现有设计；无调用级精度选项。
- 交付：增加显式精确比例/Decimal或指定小数位模式，定义舍入与尾零，允许生成可核验的报告值。修改_conversion.py、_normalization.py。
- 兼容：旧默认与特例保持，不将已说明的近似当缺陷；精确模式的128按128/255计算而非声称恰好50%。
- 正常验收：指定模式得到可复核的128/255百分比，转回原通道满足声明精度。
- 边界验收：0/255、舍入半界、极多小数位预算、非法精度及Decimal上下文变化结果明确；回归tests/test_conversion.py、tests/test_normalization.py。仅标准库decimal；依赖无。

## 10．导入颜色分量的严格校验策略

- 来源/现状：现有normalize_integer_triplet故意裁剪越界值；百分比按%分割，'50%extra'也得到50%。配置导入需要区分修正数据与拒绝错误数据。
- 交付：新增严格校验入口或显式policy，检查三通道形状、类型、有限性、完整百分比语法和范围，返回具体通道诊断。使用_types.py、_normalization.py。
- 兼容：保留旧裁剪默认；十六进制完整匹配的03是现有格式修复，本步是可选择的通道输入新合同。
- 正常验收：合法RGB/PercentRGB通过，越界值在strict下拒绝而clip下按原结果返回。
- 边界验收：bool、浮点作为整数、长度错误、一次性迭代器、NaN/Inf、缺%及多余尾字符均有明确处理；回归tests/test_normalization.py。依赖无。

## 11．查询全部颜色别名与显示偏好

- 来源/现状：hex_to_name固定返回一个规范名，names已列出gray/grey，调用方可以自行筛选全部颜色取得别名；没有直接的全别名与偏好接口。
- 交付：新增hex_to_names及显式preferred_alias策略，按规范返回稳定别名集合，并支持英美拼写/调用方优先列表。修改_definitions.py、_conversion.py。
- 兼容：原hex_to_name规范名不变；aqua/cyan、fuchsia/magenta也按实际规范数据处理，不能只修gray。
- 正常验收：#808080返回gray/grey，偏好grey可选，默认仍gray。
- 边界验收：无名称、规范差异、重复偏好、未知偏好及返回集合不可修改内部映射；回归tests/test_conformance.py、tests/test_conversion.py。依赖无。

## 12．不可变的自定义品牌色板

- 来源/现状：名称转换仅支持内建spec；brand-primary实际ValueError，当前可在业务字典自行映射。修改私有全局表会污染其他调用者。
- 交付：新增不可变Palette及名称/数值查询协议，用户色板与内建规范组合时明确名称冲突策略。新增palette模块并复用_definitions.py、_conversion.py。
- 兼容：品牌色不冒充CSS标准命名；不全局注册或改变默认spec。色板内数据复制与别名所有权明确。
- 正常验收：两个品牌同名primary互不干扰，序列化/重建后保持定义。
- 边界验收：大小写冲突、别名环、非法颜色、嵌套来源和调用方字典随后变化均明确；回归tests/test_conversion.py、tests/test_conformance.py。仅标准库；依赖无。

## 13．查找最接近的命名颜色

- 来源/现状：hex_to_name('#010101')只做精确匹配并报错；没有nearest_names，用户需自行遍历名称表计算距离。
- 交付：提供top-k近似查询，默认明确为编码sRGB通道距离，输出名称、实际颜色、距离与并列规则。修改_definitions.py、_conversion.py或新增palette模块。
- 兼容：精确查找仍报无名错误；不把RGB距离称为感知均匀距离，同值别名是否去重可选。
- 正常验收：#010101最近为black，返回距离与手工计算一致，top-k稳定。
- 边界验收：同距、别名、k为0/负/超规模、规范选择、空自定义候选与非法通道明确；回归tests/test_conversion.py、tests/test_conformance.py。使用内建色表可独立交付，不依赖12。

## 14．计算相对亮度与前背景对比度

- 来源/现状：公开函数只有格式转换，主题检查没有相对亮度/contrast API。可用现有RGB自行实现公式。
- 交付：增加声明版本的sRGB相对亮度和对比度计算，返回原始比值及明确选择的阈值判断。扩展_conversion.py或新增可访问性工具模块，依据[W3C说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)。
- 兼容：不以单个数值证明整个界面可访问性；透明输入要求先给实际背景，不能默认为白色。原颜色转换不变。
- 正常验收：黑白对比21:1、同色1:1，交换前背景比值相同。
- 边界验收：sRGB分段临界值、阈值前不四舍五入、透明背景缺失、非法通道与数值容差明确；回归tests/test_conversion.py。仅标准库，支持不透明RGB可独立交付；依赖无。

## 15．透明色按背景合成为不透明颜色

- 来源/现状：当前只有RGB，没有source-over组合入口；把alpha直接切掉不能表示透明主题色在背景上的结果。
- 交付：新增composite_over，按声明的颜色空间和预乘alpha规则计算前景覆盖背景，输出明确的RGBA或最终RGB。使用_types.py、_conversion.py及新增合成模块。
- 兼容：不把编码sRGB和线性sRGB混为同一公式输入，默认空间明确；没有背景不得暗中丢alpha。
- 正常验收：指定编码sRGB下半透明红覆盖不透明蓝得到约(128,0,128)，全透明前景保留背景。
- 边界验收：两层都透明、alpha=0/1、隐藏RGB、多个层组合顺序、精度和最终量化明确；回归tests/test_conversion.py。仅标准库；功能依赖05。

## 16．按声明空间生成颜色渐变

- 来源/现状：现有函数能转换端点，无插值或渐变合同；设计工具需手工选择空间、通道及alpha处理。
- 交付：新增interpolate/gradient，支持基本sRGB/线性sRGB及明确alpha预乘策略，输出指定数量的稳定样本。使用_conversion.py、_types.py和新增插值模块。
- 兼容：渐变插值与15前景覆盖为不同运算；不把encoded RGB平均数称作线性光混合，旧转换不变。
- 正常验收：端点保留，黑白中点随选定空间得到可核对值，多个色标在声明位置衔接。
- 边界验收：0/1样本、重复色标、反向、透明端点、超范围t及非法空间均定义；回归tests/test_conversion.py。只做RGB时独立；本路线要求alpha，功能依赖05。

## 17．显式上下文中的颜色关键字解析

- 来源/现状：name_to_rgb拒绝currentColor；HTML legacy明确拒绝transparent且应保持。内建静态色表不适合表达依赖上下文的系统色。
- 交付：新增resolve_color，区分静态名称、transparent和currentColor/受支持系统关键字，由调用方显式提供上下文并返回已解析或未解析状态。扩展_types.py、_definitions.py和新增上下文模块。
- 兼容：不修改HTML旧式算法或把系统色写入固定CSS色表；不访问浏览器/操作系统去猜主题，不求值任意CSS变量。
- 正常验收：给currentColor=#123456时准确解析，transparent保留alpha0，缺上下文返回明确未解析。
- 边界验收：上下文环、未知关键字、大小写、无效值、两主题并发互不污染；回归tests/test_conversion.py、tests/test_html5.py。标准库；功能依赖05。

## 18．本地颜色清单转换命令

- 来源/现状：pyproject.toml未声明业务console-script，包无__main__.py；批量CSV/JSONL主题资料目前需自行写Python循环。
- 交付：新增离线CLI读取明确格式的颜色记录，调用既有名称/hex/百分比入口，按记录输出目标格式与结构化错误；原始ID保持。新增__main__.py并更新pyproject.toml。
- 兼容：不下载网址或解析整个网页，默认不覆盖输入；初版只要求现有格式，不以完成其他增强为前提。
- 正常验收：中文名称字段的三行JSONL转为hex/RGB，结果与逐条原生调用一致。
- 边界验收：坏行、重复ID、空流、fail-fast/collect、stdout破管道与文件输出失败退出码明确；回归tests/test_conversion.py并新增CLI集合。标准库json/csv/argparse；依赖无。

## 19．选择最短的等价颜色字面量

- 来源/现状：rgb_to_hex固定生成六位hex，名称函数提供单个名字；没有为静态CSS输出选择最短等价写法的合同。
- 交付：新增serialize_shortest，在指定目标规范允许的名称、三/六位hex中选择最短且无损写法，定义并列稳定顺序；可随后扩展alpha格式。使用_definitions.py、_conversion.py、_normalization.py。
- 兼容：原规范化函数仍返回六位hex；不能通过近似或省alpha缩短；初版三通道独立交付。
- 正常验收：红色可选red、白色可选#fff，所有输出重新解析得到同一RGB。
- 边界验收：同长别名、大小写策略、不可缩短的通道、目标规范无名及转义/上下文关键字排除；回归tests/test_conversion.py、tests/test_conformance.py。标准库；依赖无。

## 20．跨HTML与CSS版本的颜色迁移审查

- 来源/现状：现有函数接受spec却只给单次查询/错误，HTML4的orange失败而CSS2.1成功；模板迁移需要一份原值、兼容状态与可用替代值清单。
- 交付：新增audit_colors/migrate_colors，以来源/目标规范和保真政策输出逐记录兼容说明，普通静态色可建议等价hex，无法无损表示时明确保留或拒绝。复用_definitions.py、_conversion.py并新增迁移模块。
- 兼容：不把颜色数值可表示与名称在某规范合法混为一谈；不自动替换整份HTML/CSS，也不把近似名称当无损替代。
- 正常验收：CSS2.1 orange迁往HTML4报告名称不可用但#ffa500数值可表示，原始标签与来源保留。
- 边界验收：不同gray集合、未知spec、无名称颜色、拟议alpha格式在旧目标不支持、非法记录与策略冲突均有逐项状态；回归tests/test_conformance.py、tests/test_conversion.py。仅标准库，基本静态格式可独立；依赖无。

## 冻结验收与累计回归

每步在同一真实工程保留已接受检查点，新增接口及所有错误分支由控制端独立用例验证；实际调用候选源码，观察颜色值、字面量、主题文件与CLI退出码，累计回归此前能力。原生475通过只证明固定原版的适用集合。未来实现还需准备冻结依赖与原生适配，未把上述提案、标准参考或原版缺陷观察计作模型已完成。
