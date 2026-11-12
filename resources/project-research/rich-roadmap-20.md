# Rich：二十步真实工程路线

固定 [Textualize/rich@9d8f9a372cc5916fd4781fec207ced7ddac2f08f](https://github.com/Textualize/rich/tree/9d8f9a372cc5916fd4781fec207ced7ddac2f08f)。原生基线 956 通过、25 跳过；范围和限制见 [单仓审查](./rich.md)。类型计数：{"修复": 18, "增强": 2}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．ZWJ 字素折行越界（修复）

- 来源／实际场景：[上游#4239](https://github.com/Textualize/rich/issues/4239)，窄Panel真实输入。
- 原版现状：cell_len与字素范围不一致，_split_text遍历超界抛IndexError。
- 用户交付：格宽裁切在目标超过字素累计宽度时可靠结束，Panel/Text不崩溃。
- 影响模块：cells.py:_split_text/set_cell_size；text.py:truncate。
- 兼容边界：不拆正常emoji字素，不把所有Unicode显示宽度一律设为2。
- 正常验收：给定ZWJ/中文混合串在10列Panel成功输出且内容有序。
- 边界／错误验收：零宽字素、位置超出、非BMP/组合字符与正常ASCII裁切一致且不死循环。
- 原生回归：tests/test_cells.py、tests/test_text.py、tests/test_panel.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．循环异常链有界提取（修复）

- 来源／实际场景：[上游#4238](https://github.com/Textualize/rich/issues/4238)；双异常cause/context子进程复现。
- 原版现状：Traceback.extract一直追加Stack，0.5秒超时才回收。
- 用户交付：按异常对象身份检测整个链及group的已访问节点，每个对象至多提取一次。
- 影响模块：traceback.py:Traceback.extract。
- 兼容边界：正常cause/context顺序与__suppress_context__保持；不按相同异常文字误去重。
- 正常验收：两/三对象循环立即返回，普通异常链完整。
- 边界／错误验收：self-cycle、ExceptionGroup共享成员、不可hash异常子类与混合链接有界。
- 原生回归：tests/test_traceback.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．负整数索引保留样式（修复）

- 来源／实际场景：[上游#4237](https://github.com/Textualize/rich/issues/4237)，Text[-1]与Text[4]对照。
- 原版现状：字符相同但负索引span为空。
- 用户交付：归一负索引后按相同字符偏移截取span，保留Text自身style。
- 影响模块：text.py:Text.__getitem__。
- 兼容边界：越界仍IndexError，切片规则保持，不把负索引钳成0。
- 正常验收：bold hello的[-1]与[4]字符/样式等价。
- 边界／错误验收：-len、过小/过大、空串、交叠span和Unicode字符边界正确。
- 原生回归：tests/test_text.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．非正格宽一致收口（修复）

- 来源／实际场景：[上游#4234](https://github.com/Textualize/rich/issues/4234)、[#4211](https://github.com/Textualize/rich/issues/4211)与原生矩阵。
- 原版现状：窄字符width0触发range步长0，负total保留abcde，而宽字符得到空。
- 用户交付：定义无可用格宽时裁切/折行为空且不保留正文，避免快慢路径差异。
- 影响模块：cells.py:set_cell_size/chop_cells；text.py:wrap。
- 兼容边界：正宽度行为保持；对外说明<=0返回空字符串/空Lines的统一边界。
- 正常验收：ASCII和中文在0/负宽度均不崩溃且无残留内容。
- 边界／错误验收：空输入、极小宽度、父容器内缩导致0以及折行溢出控制一致。
- 原生回归：tests/test_cells.py、tests/test_text.py、tests/test_columns.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．ANSI 解析不泄漏伪装的 ESC（修复）

- 来源／实际场景：[上游#4233](https://github.com/Textualize/rich/issues/4233)；ESC-NUL-[31m合成输入。
- 原版现状：Text.from_ansi结果仍含ESC和后续序列。
- 用户交付：对控制序列中的可忽略C0字符有明确解析/丢弃策略，解码文本不保留意外活跃ESC。
- 影响模块：ansi.py:re_ansi/_ansi_tokenize/AnsiDecoder。
- 兼容边界：标准SGR/OSC8解析保持；不宣称此入口是任意终端协议的完整安全清洗器。
- 正常验收：正常SGR保留RED文本并带样式，NUL变体不残留ESC。
- 边界／错误验收：多个C0、截断CSI、OSC/ST、换行/制表符和纯文本不被错误吞掉。
- 原生回归：tests/test_ansi.py、tests/test_text.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．空高亮词集合不产生匹配（修复）

- 来源／实际场景：[上游#4229](https://github.com/Textualize/rich/issues/4229)，highlight_words([])实测。
- 原版现状：abc产生4个零长度span且count4。
- 用户交付：空词集合返回0并保持原Text/span完全不变。
- 影响模块：text.py:Text.highlight_words。
- 兼容边界：非空substring匹配默认语义保持，空字符串词的策略明确。
- 正常验收：空list/tuple/generator均无更改，正常词高亮保持。
- 边界／错误验收：已有span、不区分大小写、集合含空串、重复词不制造零长伪匹配。
- 原生回归：tests/test_text.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．非字符串 SyntaxError 消息可靠显示（修复）

- 来源／实际场景：[上游#4225](https://github.com/Textualize/rich/issues/4225)，ParseError(ExpatError)原生场景。
- 原版现状：渲染时二次TypeError掩盖原XML异常。
- 用户交付：使用安全字符串转换规范化syntax_error.msg等字段，失败时有稳定占位文本。
- 影响模块：traceback.py:extract及语法错误渲染。
- 兼容边界：原字符串消息、代码行/offset标注保持，不改变异常对象。
- 正常验收：ParseError原消息可见且不会抛新异常。
- 边界／错误验收：msg对象__str__也抛错、空消息、非法offset和ExceptionGroup内错误可靠。
- 原生回归：tests/test_traceback.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．Console.print 尊重 Text 自带排版（修复）

- 来源／实际场景：[上游#4216](https://github.com/Textualize/rich/issues/4216)，center Text直接print与显式参数对照。
- 原版现状：sep_text.join以分隔符排版覆盖原Text.justify，输出hi不居中。
- 用户交付：单个Text保留自身justify/overflow/no_wrap，print显式覆盖优先级明确。
- 影响模块：console.py:_collect_renderables；text.py:join/blank_copy。
- 兼容边界：多个不同排版Text的合并策略单独明确；普通str和sep/end保持。
- 正常验收：20列打印center Text与显式center结果一致。
- 边界／错误验收：显式left覆盖、多个Text、软折行、end空串、Panel/Group路径不回归。
- 原生回归：tests/test_console.py、tests/test_text.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．SVG 所有行引用都有定义（修复）

- 来源／实际场景：[上游#4215](https://github.com/Textualize/rich/issues/4215)，实际SVG引用集合。
- 原版现状：三行内容引用line-0/1/2，但只定义0/1。
- 用户交付：按实际行数生成全部clipPath，最后行可正常绘制。
- 影响模块：console.py:Console.export_svg。
- 兼容边界：unique_id、主题和输出模板保持；不把此修复等同于所有字体几何问题解决。
- 正常验收：单/三行SVG的每个line引用都有且仅有一个目标。
- 边界／错误验收：空record、尾部空行、背景、Unicode和自定义unique_id形成合法XML。
- 原生回归：tests/test_console.py；独立XML解析/引用对账。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．过宽 Columns 降级布局（修复）

- 来源／实际场景：[上游#4214](https://github.com/Textualize/rich/issues/4214)，width100放10列console。
- 原版现状：column_count变0触发modulo/division by zero。
- 用户交付：可用列数下界1，按容器宽度裁切/折行，不因请求宽度过大崩溃。
- 影响模块：columns.py:Columns.__rich_console__。
- 兼容边界：正常多列、equal/column_first/right_to_left排版保持。
- 正常验收：1/2个元素在过窄容器都能渲染。
- 边界／错误验收：width0/负值按明确参数规则拒绝，padding大于容器、空列表、超宽中文稳定。
- 原生回归：tests/test_columns.py、tests/test_measure.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．保存文本失败保留记录（修复）

- 来源／实际场景：[上游#4208](https://github.com/Textualize/rich/issues/4208)，missing目录真实写入失败。
- 原版现状：save_text先export(clear=True)，失败后record内容已丢。
- 用户交付：只有文件写入成功后才移除这次已保存的记录范围，允许失败重试。
- 影响模块：console.py:Console.save_text/export_text/_record_buffer_lock。
- 兼容边界：clear=False仍保留；并发新记录不能在成功后被全部误清。
- 正常验收：成功保存文字正确且按clear策略处理，失败后仍可export原内容。
- 边界／错误验收：open/write/close失败、Unicode、追加新记录与空record不丢失或重复清除。
- 原生回归：tests/test_console.py；独立文件读回/失败注入。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．cwd 无权限时可导入（修复）

- 来源／实际场景：[上游#4201](https://github.com/Textualize/rich/issues/4201)，单独子进程PermissionError注入。
- 原版现状：import rich在getcwd调用处直接PermissionError。
- 用户交付：与已存在的删除cwd回退一致，预期OSError使用空_IMPORT_CWD，延后依赖cwd操作报错。
- 影响模块：rich/__init__.py；traceback.py使用_IMPORT_CWD。
- 兼容边界：不忽略任意编程错误，不为导入变更全局cwd。
- 正常验收：PermissionError/缺cwd条件下导入及绝对路径工作仍可用。
- 边界／错误验收：EACCES/EPERM/OSError、正常cwd、相对回溯路径回退清楚。
- 原生回归：tests/test_rich_print.py、tests/test_traceback.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 13．NBSP 保留不换行单元（修复）

- 来源／实际场景：[上游#4196](https://github.com/Textualize/rich/issues/4196)、[#3545](https://github.com/Textualize/rich/issues/3545)；xx aa-NBSP-bb。
- 原版现状：6列拆成xx aa-NBSP与bb，在NBSP处断行。
- 用户交付：词边界区分可换行空格与NBSP，能放下一行的组合保持完整。
- 影响模块：_wrap.py:words/divide_line；text.py:wrap。
- 兼容边界：超出整行的单元仍遵守fold/crop/ellipsis显式策略，不承诺永不超宽。
- 正常验收：示例换成xx和完整aa-NBSP-bb两行。
- 边界／错误验收：前后普通空格、连续NBSP、窄宽度、组合字素和overflow选项一致。
- 原生回归：tests/test_text.py、tests/test_panel.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．可选完整词高亮（增强）

- 来源／实际场景：[上游#4194](https://github.com/Textualize/rich/issues/4194)；GET/FORGET/GETTER观察。
- 原版现状：默认substring模式把三处GET都高亮，RichHandler关键字也使用同入口。
- 用户交付：增加显式whole_words模式与Unicode词边界策略，日志关键字可选择完整词。
- 影响模块：text.py:highlight_words；logging.py:render_message。
- 兼容边界：默认substring保持；不把现有一般子串能力直接删掉。
- 正常验收：开启模式只高亮独立GET，默认仍3处。
- 边界／错误验收：标点、下划线、中文相邻、带连字符词与regex特殊符安全处理。
- 原生回归：tests/test_text.py、tests/test_logging.py。
- 实际功能依赖：06。

### 15．异常 notes 归属正确异常（修复）

- 来源／实际场景：[上游#3960](https://github.com/Textualize/rich/issues/3960)；outer加note的两异常链。
- 原版现状：外层notes被读一次复用到inner Stack。
- 用户交付：逐异常获取/复制notes，只在有该note的异常上显示。
- 影响模块：traceback.py:Traceback.extract/Stack。
- 兼容边界：原异常顺序保持；同一文字不同异常notes不能按文本全局去重。
- 正常验收：outer note只显示一次，inner自己的note各自保留。
- 边界／错误验收：空notes、自定义对象、ExceptionGroup共享成员、循环链与样式不串。
- 原生回归：tests/test_traceback.py。
- 实际功能依赖：02。

### 16．日志格式错误走 handleError（修复）

- 来源／实际场景：[上游#3536](https://github.com/Textualize/rich/issues/3536)，坏格式LogRecord实际emit。
- 原版现状：TypeError从self.format逃逸，handleError未被调用。
- 用户交付：将预期日志格式/渲染失败交给标准handler错误策略，不中断业务调用。
- 影响模块：logging.py:RichHandler.emit。
- 兼容边界：遵循logging.raiseExceptions诊断策略；不吞KeyboardInterrupt/SystemExit。
- 正常验收：坏%参数调用返回且handleError收到原record，合法消息后续仍输出。
- 边界／错误验收：Formatter抛错、异常回溯格式、markup错误、NullFile与输出编码失败不递归logging。
- 原生回归：tests/test_logging.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．ANSI CRLF 不丢正文（修复）

- 来源／实际场景：[上游#4090](https://github.com/Textualize/rich/issues/4090)，Hello CRLF World CRLF。
- 原版现状：from_ansi得到两个空行，而LF对照正常。
- 用户交付：先识别CRLF行尾，再保留独立CR作为回车覆盖的语义。
- 影响模块：ansi.py:AnsiDecoder.decode/decode_line；text.py:from_ansi。
- 兼容边界：已有foo-CR-bar进度覆写保持，不简单删除所有CR。
- 正常验收：CRLF/LF两种文本保留相同正文与正常行数。
- 边界／错误验收：混合换行、尾CR、多个CR、SGR跨行和空行行为明确。
- 原生回归：tests/test_ansi.py、tests/test_text.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．Progress 停止后 reset 重启时钟（修复）

- 来源／实际场景：[上游#3705](https://github.com/Textualize/rich/issues/3705)，显式get_time受控观察。
- 原版现状：stop_time105在reset到110后仍保留，elapsed=-5且之后不动。
- 用户交付：reset清理停止/结束时钟并按start参数设置新计时，start_task恢复语义明确。
- 影响模块：progress.py:Task._reset/Progress.reset/start_task/stop_task。
- 兼容边界：stop_task冻结时长仍保持；reset是新计时不暗积累旧任务时间。
- 正常验收：100开始105停止为5，110reset后120为10。
- 边界／错误验收：start=False、未开始任务、已完成任务、多次停止/重置和速度估计不串。
- 原生回归：tests/test_progress.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．RichHandler 输出时区偏移（修复）

- 来源／实际场景：[上游#3877](https://github.com/Textualize/rich/issues/3877)，时间0+%z观察。
- 原版现状：datetime.fromtimestamp生成naive时间，%z为空。
- 用户交付：按本地时区创建有时区的日志时间，格式中的%z/%Z可见。
- 影响模块：logging.py:RichHandler.render；_log_render.py。
- 兼容边界：不改变LogRecord.created原值；调用者日期格式/自定义时间函数保持。
- 正常验收：UTC输出+0000，受控非UTC时区输出对应偏移。
- 边界／错误验收：夏令时边界、重复时间隐藏、Formatter.datefmt、无%z默认格式不变。
- 原生回归：tests/test_logging.py、tests/test_log.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．Prompt 选项分隔符可配置（增强）

- 来源／实际场景：[上游#3552](https://github.com/Textualize/rich/issues/3552)，Prompt.make_prompt实际输出a/b。
- 原版现状：separator硬编码为/，公开构造与ask均无可选参数。
- 用户交付：增加choices_separator选项，让ask和实例一致使用逗号/竖线等，选择值语义保持。
- 影响模块：prompt.py:PromptBase.__init__/ask/make_prompt。
- 兼容边界：默认/保持；不把choices本身改变成新的字符串值。
- 正常验收：逗号或竖线输出正确且输入a仍通过原选择校验。
- 边界／错误验收：空分隔符、含markup/Unicode、show_choices=False、默认值和Confirm子类兼容。
- 原生回归：tests/test_prompt.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

保留既有颜色环境控制、Table/Panel/Markdown、markup、进度嵌套/Live、HTML/SVG/文本导出、自定义高亮与日志处理、Prompt子类化等能力。上游doc/test修正、删除sqrt、版本说明、未断言测试和旧issue本身不计用户功能。CJK ambiguous宽度需终端策略决定，未未经取舍直接改成2格；Jupyter/Windows报告未在本轮环境复现，不列已证实修复。SVG本轮只验证XML引用完整性，没有声称已进行跨浏览器字体/像素验收。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
