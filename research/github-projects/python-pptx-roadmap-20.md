# python-pptx：二十步真实工程迭代路线

固定 [scanny/python-pptx@278b47b1dedd5b46ee84c286e77cdfb0bf4594be](https://github.com/scanny/python-pptx/tree/278b47b1dedd5b46ee84c286e77cdfb0bf4594be)，详见[单仓审查](./python-pptx.md)。共 20 步：19 项增强提案、1 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．RGB 十六进制输入严格为六位（问题修复）

- 来源／场景：https://github.com/scanny/python-pptx/issues/1151
- 原版现状：RGBColor.from_string按前2/中2/剩余切片；11223和1122000当前被接受并变成其他颜色。
- 交付目标：校验输入为恰好六位十六进制字符，错误使用清晰ValueError。
- 影响模块：src/pptx/dml/color.py:RGBColor.from_string
- 兼容边界：合法大小写输入继续可用；不把CSS #rgb/#rrggbb默认为当前API支持。
- 正常验收：112233/abcdef得到预期颜色，5/7位字符串均被拒绝。
- 异常／边界：空串、非str、非hex、前缀#、空白和Unicode类数字，序列化仍六位大写。
- 原生回归：tests/dml/test_color.py；features/dml-color
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．幻灯片复制移动与删除的关系管理（增强提案）

- 来源／场景：slide.py:Slides只有add_slide/get/index；固定源码：[src/pptx/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/slide.py)、[src/pptx/parts/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/parts/slide.py)。
- 原版现状：修改私有sldIdLst能重排但不会安全迁移图表/图片/备注/布局关系，无公共生命周期操作。
- 交付目标：提供同包clone/move/remove，重映射共享和独占部件并维护所有被引用关系。
- 影响模块：Slides；PresentationPart/SlidePart；OPC package
- 兼容边界：首版同演示文稿；跨包导入由单独布局导入政策处理，不盲目deepcopy。
- 正常验收：复制含表/图/图片/备注的页后独立编辑，移动/删除不丢其他页内容。
- 异常／边界：内部跳转指向删除页、被共享chart/图片、最后一页和失败无半部件。
- 原生回归：test_slide/parts.slide/OPC；实际PPTX重开
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．演示文稿批注线程（增强提案）

- 来源／场景：slide.py及parts目录无公开Comments代理；固定源码：[src/pptx/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/slide.py)、[src/pptx/parts/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/parts/slide.py)。
- 原版现状：普通备注已可编辑，但不是挂在页/作者上的批注线程；批注部件只能原样保留。
- 交付目标：新增页批注集合，首版传统批注作者/位置/时间/内容及明确的回复支持范围。
- 影响模块：新增comments parts/代理；SlidePart；OPC注册
- 兼容边界：不把notes_slide当comments；新版云端modern comments未支持时明确只读。
- 正常验收：页内两位合成作者批注保存重开，关系及作者ID唯一。
- 异常／边界：缺作者、重复ID、删除最后批注、未知新版扩展和跨页复制。
- 原生回归：OPC/slide模式；独立comments XML/关系验收
- 真实依赖：02

## 04．页面切换效果（增强提案）

- 来源／场景：Slide代理只提供背景/形状/布局等，无transition属性；固定源码：[src/pptx/oxml/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/oxml/slide.py)。
- 原版现状：现有文件切换XML可保留，但无公开设置fade/push及持续时间接口。
- 交付目标：提供Slide.transition，首版fade/push/wipe、点击/定时前进。
- 影响模块：slide.py；oxml/slide.py；枚举与验证
- 兼容边界：默认无新增效果；不执行自动播放，保留未知效果扩展。
- 正常验收：设置fade与3秒前进后XML参数完整，重开读回。
- 异常／边界：负持续时间、非法方向、清除效果、已有未知transition及连续保存。
- 原生回归：tests/test_slide.py/oxml.slide；fixture对照
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．基础形状进入动画序列（增强提案）

- 来源／场景：shapetree只为movie添加特定timing，无一般动画API；固定源码：[src/pptx/shapes/shapetree.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/shapes/shapetree.py)。
- 原版现状：视频播放timing不等于任意形状动画；普通appear/fade动画需手工写复杂时间树。
- 交付目标：新增显式AnimationSequence，首版appear/fade、按点击/与上一项/之后及delay。
- 影响模块：slide timing代理；oxml动画；shape ID关联
- 兼容边界：不承诺完整PowerPoint动画编辑器；未知动画保留，不能重写整个原timing。
- 正常验收：三项形状依次进入，动画目标指向正确spid，重开可枚举。
- 异常／边界：删除/复制目标形状、重复ID、空序列、非法时长与movie timing共存。
- 原生回归：shapetree timing测试；独立时间树解析
- 真实依赖：02, 04

## 06．导入布局母版与主题（增强提案）

- 来源／场景：SlideLayouts可读/删除，不能从其他presentation导入；固定源码：[src/pptx/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/slide.py)、[src/pptx/parts/slide.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/parts/slide.py)。
- 原版现状：调用方复制页XML不能迁移layout/master/theme及字体/图片关系。
- 交付目标：提供import_layout显式导入相关母版/主题图，去重并定义同名政策。
- 影响模块：SlideLayouts/SlideMasters；parts.slide；OPC关系
- 兼容边界：不自动套用其他包所有主题；不改变已有页母版或重写未支持部件。
- 正常验收：从合成模板导入一个布局后新页继承其背景/占位符/主题。
- 异常／边界：同名布局、重复母版、共享图片、缺关系及外部关系不联网。
- 原生回归：slide/master/OPC；两包导入文件验收
- 真实依赖：02

## 07．幻灯片节分组（增强提案）

- 来源／场景：Presentation.slides线性集合无section代理；固定源码：[src/pptx/presentation.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/presentation.py)。
- 原版现状：没有公开p14 sectionLst管理，长课件按章节分组需手写扩展XML。
- 交付目标：新增Sections集合，按稳定slide_id添加/改名/移动节并维护页归属。
- 影响模块：presentation.py；oxml.presentation扩展；Slides
- 兼容边界：不把slide_layout当章节；旧文件无节时保持原包，无需生成空扩展。
- 正常验收：十页划分三节，重排页面后节归属按明确政策保持。
- 异常／边界：空节、重复名、跨节移动、删除首末页和未知扩展保留。
- 原生回归：presentation/slide测试；节扩展XML
- 真实依赖：02

## 08．表格中间行列编辑（增强提案）

- 来源／场景：Table公开rows/columns/cell/merge但无insert/delete；固定源码：[src/pptx/oxml/table.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/oxml/table.py)。
- 原版现状：直接移tc/tr可能破坏合并网格、列宽和表整体尺寸。
- 交付目标：提供插入/删除行列，首版明确处理合并区域并更新尺寸。
- 影响模块：table.py；oxml/table.py；GraphicFrame几何
- 兼容边界：默认现有表不变；复杂不能保持的span操作先拒绝，禁止静默破坏。
- 正常验收：在库存表中间插行/删除列，数据顺序、宽高与合并边界正确。
- 异常／边界：删除merge origin、跨span插列、最后行列、0尺寸和已有损坏表。
- 原生回归：tests/test_table.py；features/tbl-*
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．单元格边框及表格样式设置（增强提案）

- 来源／场景：_Cell有fill/margins/text，缺少公共边框与table style选择；固定源码：[src/pptx/oxml/table.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/oxml/table.py)。
- 原版现状：边框需私有tcPr和lnL/lnR等XML，Table只有banding/首末行列开关。
- 交付目标：提供CellBorders及显式表样式ID/自定义主题样式引用。
- 影响模块：table.py；dml/line；oxml/table.py；tableStyles关系
- 兼容边界：原fill/margin功能保留不重算；直接边框与样式继承优先级清楚。
- 正常验收：标题外框与数据细线、表样式引用保存重开一致。
- 异常／边界：None清除、主题色、dash、合并边界、未知样式ID与非法宽度。
- 原生回归：table/dml line/oxml测试；独立边框XML
- 真实依赖：08

## 10．解除组合保持页坐标（增强提案）

- 来源／场景：GroupShapes支持添加组合与recalculate_extents，无ungroup公共入口；固定源码：[src/pptx/shapes/group.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/shapes/group.py)、[src/pptx/shapes/shapetree.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/shapes/shapetree.py)。
- 原版现状：把组内XML直接移到slide会忽略chOff/chExt变换，形状视觉位置尺寸改变。
- 交付目标：新增ungroup应用父组坐标变换到子形状，保留Z顺序和必要关系。
- 影响模块：shapes/group.py/shapetree.py；oxml groupshape/xfrm
- 兼容边界：首版明确旋转/翻转与嵌套组支持边界；不把已有add_group_shape当新增。
- 正常验收：平移缩放组合解除后子形状page bounding boxes相同。
- 异常／边界：嵌套组、0 chExt、旋转/翻转、连接线端点及动画引用。
- 原生回归：tests/shapes/test_group.py/test_shapetree.py
- 真实依赖：02, 05

## 11．SVG 图片与 PNG 回退（增强提案）

- 来源／场景：parts/image.py以Pillow元数据识别图像；无SVG公共插图路径；固定源码：[src/pptx/parts/image.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/parts/image.py)。
- 原版现状：普通add_picture对SVG不能获得标准像素尺寸与回退，需用户手工组装扩展图片关系。
- 交付目标：提供显式SVG+用户提供PNG回退输入，生成asvg扩展、正确viewBox与尺寸。
- 影响模块：image parts；shapes.add_picture；oxml picture；content types
- 兼容边界：不联网加载SVG外部资源，不引入未声明渲染器；fallback由调用方提供。
- 正常验收：包含SVG和PNG两部件及正确关系，支持端用矢量、其他端用回退。
- 异常／边界：坏SVG/无viewBox、外部引用政策、流/尺寸、重复图片去重和透明背景。
- 原生回归：image/picture/OPC测试；SVG扩展fixture
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．形状替代文本和装饰标记（增强提案）

- 来源／场景：BaseShape有name/id，未公开cNvPr descr/title属性；固定源码：[src/pptx/shapes/base.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/shapes/base.py)。
- 原版现状：辅助阅读描述需私有XML；名称不是可访问替代文本。
- 交付目标：增加alt_text/title/decorative，并提供按页枚举缺描述对象。
- 影响模块：shapes/base.py；oxml nonvisual属性；presentation审查辅助
- 兼容边界：不从文件名猜描述；默认不重写已有内容，无描述图表也应可报告。
- 正常验收：图片/图表写说明后保存重开，独立XML可核对。
- 异常／边界：Unicode、空值清除、组子项、decorative冲突及未知扩展保持。
- 原生回归：shapes/base/picture测试；真实文件检查
- 真实依赖：11

## 13．创建多绘图区组合图（增强提案）

- 来源／场景：chart读模型有plots，创建图writer按单chart_type生成；固定源码：[src/pptx/chart/data.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/chart/data.py)、[src/pptx/chart/xmlwriter.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/chart/xmlwriter.py)。
- 原版现状：读到多plot不等于可以公开创建柱线组合图；无组合写入API。
- 交付目标：扩展ChartData构建明确的组合plot集合，分配series顺序与缓存/工作簿区域。
- 影响模块：chart/data.py/xmlwriter.py；chart.py/plot.py；嵌入XLSX
- 兼容边界：首版column+line；不泛化所有图表类型，保留原单类型接口。
- 正常验收：销售柱+利润线共图，嵌入工作簿与每plot缓存一致。
- 异常／边界：空series、categories不等、重复series ID、修改replace_data后的顺序。
- 原生回归：chart xmlwriter/data/plot；独立嵌入工作簿检查
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．图表主副轴的公开关联（增强提案）

- 来源／场景：Chart.category_axis/value_axis通常取第一个匹配轴；固定源码：[src/pptx/chart/xmlwriter.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/chart/xmlwriter.py)。
- 原版现状：需要组合图第二数值轴时缺少按轴ID/绘图区选择和创建的稳定API。
- 交付目标：提供axes集合与plot axis_group，正确创建axId/crossAx主副轴关系。
- 影响模块：chart/chart.py/axis.py/xmlwriter.py；oxml chart
- 兼容边界：默认访问仍兼容首轴；不把任意轴ID当图表series ID。
- 正常验收：利润线使用右侧百分比轴，柱形仍用左侧金额轴，关系闭合。
- 异常／边界：日期/对数轴、同类多轴、删plot后孤立轴及非法交叉关系。
- 原生回归：tests/chart/test_axis.py/test_xmlwriter.py
- 真实依赖：13

## 15．段落项目符号与编号配置（增强提案）

- 来源／场景：_Paragraph公开level/格式，但项目符号多靠layout继承；固定源码：[src/pptx/text/text.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/text/text.py)、[src/pptx/oxml/text.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/oxml/text.py)。
- 原版现状：level不等于可设置bullet char/font、无项目符号或auto-number类型与起始值。
- 交付目标：新增bullet配置，支持none/字符/常见自动编号，维护继承与缩进关系。
- 影响模块：text/text.py；oxml/text.py；枚举
- 兼容边界：默认继承保持；不把编号文字直接拼到text。
- 正常验收：一级圆点二级数字列表输出buChar/buAutoNum，清除可恢复继承。
- 异常／边界：空段、起始数、未知字体、与placeholder默认样式及level0-8。
- 原生回归：tests/text/test_text.py；features/txt-paragraph
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．文本方向和竖排（增强提案）

- 来源／场景：TextFrame.vertical_anchor只是上下对齐，未公开bodyPr vert；固定源码：[src/pptx/text/text.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/text/text.py)、[src/pptx/oxml/text.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/oxml/text.py)、[src/pptx/enum/text.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/enum/text.py)。
- 原版现状：竖排中文和旋转文本需私有XML，现有vertical_anchor不能实现文字方向。
- 交付目标：提供text_direction枚举horizontal/vertical/eastAsian等明确模式。
- 影响模块：text/text.py:TextFrame；oxml/text.py；enum/text.py
- 兼容边界：不改变vertical_anchor定义；保留未知方向值可读状态，不擅自旋转整个shape。
- 正常验收：中文标题竖排，保存重开bodyPr vert正确，水平默认不变。
- 异常／边界：自动适应、旋转角、空文本、表格单元格与主题字体。
- 原生回归：text/oxml text；真实方向fixture
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．跨文本运行替换保持样式（增强提案）

- 来源／场景：TextFrame.text/Paragraph.text赋值重建运行；模板填充场景；固定源码：[src/pptx/text/text.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/text/text.py)。
- 原版现状：标记可分散在不同runs，整体text替换会丢run级格式/链接。
- 交付目标：新增replace_text按字符映射修改命中run范围，明确新文本的继承样式。
- 影响模块：text/text.py；超链接/action；shape文本访问
- 兼容边界：不跨页/shape；默认text setter保留旧语义；字段/软换行边界显式。
- 正常验收：${customer}分两run仍可替换，旁边粗体/颜色/链接保持。
- 异常／边界：重叠匹配、空替换、垂直制表换行、field节点、表格和备注story。
- 原生回归：tests/text/test_text.py；真实模板保存重开
- 真实依赖：15, 16

## 18．多形状对齐和等距分布（增强提案）

- 来源／场景：BaseShape提供单独left/top/width/height，无批量布局接口；固定源码：[src/pptx/shapes/base.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/shapes/base.py)。
- 原版现状：用户需自行计算多个形状的边界、分组坐标和固定端点。
- 交付目标：提供align/distribute，显式参考页/选区/锚点对象，返回变更几何。
- 影响模块：shapes布局辅助；group变换；BaseShape
- 兼容边界：仅设置几何不进行字体排版；不自动修改shape尺寸除非显式。
- 正常验收：三张卡片左右对齐并等间距，首末端点保持，单位为EMU。
- 异常／边界：少于两项、旋转对象bounds规则、不同组、锁定/0尺寸与舍入余量。
- 原生回归：shape/group几何测试；数值位置独立断言
- 真实依赖：10

## 19．自定义文稿属性（增强提案）

- 来源／场景：Presentation.core_properties仅Dublin Core；交付版本审计场景；固定源码：[src/pptx/parts/coreprops.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/parts/coreprops.py)。
- 原版现状：无公共custom.xml属性集合，业务模板版本/审阅状态需修改ZIP。
- 交付目标：新增custom_properties类型化集合，维护pid/fmtid、内容类型和包关系。
- 影响模块：新增customprops part；parts/presentation；OPC
- 兼容边界：不改变核心属性；未知variant无损保留/只读，不转换成错误类型。
- 正常验收：写TemplateVersion/Approved并重开类型不变，更新属性不重复ID。
- 异常／边界：重名、空名、非法数值、UTC时间、删除最后项与跨包母版导入。
- 原生回归：OPC/coreprops模式；独立custom.xml解析
- 真实依赖：06

## 20．包结构预检与读取预算（增强提案）

- 来源／场景：opc/package.py与serialized.py读取部件；用户上传课件场景；固定源码：[src/pptx/opc/package.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/opc/package.py)、[src/pptx/opc/serialized.py](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/src/pptx/opc/serialized.py)。
- 原版现状：没有公开ZIP部件/字节预算或完整关系/shape ID预检报告，坏输入常在下游属性访问时失败。
- 交付目标：提供PackageLimits及validate，限制部件/解压总量/XML深度并报告悬挂关系/重复ID/非法引用。
- 影响模块：opc/serialized.py/package.py；oxml parser；presentation.validate
- 兼容边界：默认读取兼容；不声称实现完整OOXML验证器，外部关系只报告不访问。
- 正常验收：合成缺图关系定位到slide/rel；超限包在加载前受控拒绝。
- 异常／边界：循环合法关系、重复ZIP名称、外部URL、未知扩展、只读输入和检查预算。
- 原生回归：全部2700单测+973BDD；独立损坏包夹具
- 真实依赖：02, 05, 06, 13, 19

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
