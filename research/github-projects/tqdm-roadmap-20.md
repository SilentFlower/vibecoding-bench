# tqdm：二十步真实工程路线

固定 [tqdm/tqdm@9cf5a12b1f955468a17f0ba3c59092b23e4258ac](https://github.com/tqdm/tqdm/tree/9cf5a12b1f955468a17f0ba3c59092b23e4258ac)。原生基线 175 通过、4 跳过；范围和限制见 [单仓审查](./tqdm.md)。类型计数：{"修复": 16, "增强": 4}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．组合迭代repeat遵守整数索引协议（修复）

- 来源／实际场景：[上游#1858](https://github.com/tqdm/tqdm/issues/1858)；product与itertools.product直接对照。
- 原版现状：__index__对象被指数运算拒绝；NumPy int64的16**16总数溢出为0。
- 用户交付：通过operator.index规范化repeat，校验后用Python整数计算精确总量；不改变元素产出。
- 影响模块：contrib/itertools.py:product。
- 兼容边界：显式total优先；未知长度不预消费；保留itertools的负repeat错误类别。
- 正常验收：自定义Repeat(2)产生9项，NumPy repeat=16的首项显示精确18446744073709551616。
- 边界／错误验收：负值/零次/空输入/非整数、显式total及极大整数总量保持标准库语义。
- 原生回归：tests/tests_itertools.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．OSC8链接按可见标签计算和裁剪（修复）

- 来源／实际场景：[上游#1856](https://github.com/tqdm/tqdm/issues/1856)；disp_len/disp_trim实测。
- 原版现状：docs链接被计37列而非4，裁4列得到未闭合ESC]8;。
- 用户交付：解析OSC8控制区与可见标签，裁剪不切断控制序列，保留正确闭合。
- 影响模块：utils.py:RE_ANSI/disp_len/disp_trim；std.py:format_meter。
- 兼容边界：保留现有CSI/SGR行为；未知OSC不误当可见URL，不执行控制码。
- 正常验收：带链接和普通docs在同ncols下留下相同条形与计数空间。
- 边界／错误验收：BEL/ST结尾、空URL闭合、多链接、宽字标签、非法/截断输入处理有界。
- 原生回归：tests/tests_utils.py；tests/tests_tqdm.py:test_ANSI_escape_codes。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．跨读取边界识别多字节分隔符（修复）

- 来源／实际场景：[上游#1847](https://github.com/tqdm/tqdm/issues/1847)；真实CLI é分隔/缓冲2字节。
- 原版现状：1é2é3计2项；--update把1é2当一条数字SyntaxError并截断透传。
- 用户交付：在保留尾部和新块组合后识别完整分隔符，计数/数字更新正确且原字节不变。
- 影响模块：cli.py:posix_pipe/main。
- 兼容边界：默认换行、NUL、bytes模式和末尾无分隔记录保持；不把整个输入读入内存。
- 正常验收：普通计3项、update累加6，stdout逐字节等于输入。
- 边界／错误验收：分隔符每个边界位置、连续/末尾分隔、EOF半个分隔、空输入、超长记录策略明确。
- 原生回归：tests/tests_main.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．IO包装报告真正写入数量（修复）

- 来源／实际场景：[上游#1845](https://github.com/tqdm/tqdm/issues/1845)；memoryview(array I)实写12回调3。
- 原版现状：write回调使用len(data)，与二进制流返回字节数不一致。
- 用户交付：标准写返回有效整数时按实际成功数更新，返回None流保留明确兼容回退。
- 影响模块：utils.py:CallbackIOWrapper。
- 兼容边界：返回值透传；文本流的计数单位保持字符，不一律把str当UTF-8字节。
- 正常验收：12字节memoryview得到回调12，短写只报告成功部分。
- 边界／错误验收：None/0/非法返回、短写重试归调用方、写异常不得先递增，read路径保持。
- 原生回归：tests/tests_utils.py；tests/tests_tqdm.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．CLI日志选项产生可理解的参数错误（修复）

- 来源／实际场景：[上游#1827](https://github.com/tqdm/tqdm/issues/1827)；真实--log空值/未知值。
- 原版现状：分别IndexError/AttributeError堆栈，绕过统一参数错误处理。
- 用户交付：缺值与未知级别在解析阶段给usage/说明和非零退出，无内部堆栈。
- 影响模块：cli.py:main日志级别解析/cast。
- 兼容边界：合法INFO/DEBUG及--log=形式保持；help/version不被无关坏日志参数阻断的优先级明确。
- 正常验收：合法级别正常透传；缺值和NOTALEVEL输出针对log的可读提示。
- 边界／错误验收：空值、小写策略、非字符串logging属性、重复参数和管道内容转发错误策略清楚。
- 原生回归：tests/tests_main.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．非法十六进制颜色沿用未知色降级（修复）

- 来源／实际场景：[上游#1826](https://github.com/tqdm/tqdm/issues/1826)；Bar颜色构造实测。
- 原版现状：普通未知色warn并关闭颜色，#00ff0g直接ValueError。
- 用户交付：统一验证格式，非法HEX按既有未知色warning退回无颜色，主循环继续。
- 影响模块：std.py:Bar.colour。
- 兼容边界：保留合法RGB和名称，不将数值异常静默吞成其他颜色。
- 正常验收：合法#00ff00正确，非法HEX仅发一次TqdmWarning且返回无色条。
- 边界／错误验收：缺位/多位、非str、大小写、动态改色与warnings-as-errors均有明确语义。
- 原生回归：tests/tests_tqdm.py:test_colour。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．网络响应创建前保留原始异常（修复）

- 来源／实际场景：[上游#1812](https://github.com/tqdm/tqdm/issues/1812)；假Session连接异常双组件实测。
- 原版现状：DiscordIO/TelegramIO的req未赋值，except又读status_code，UnboundLocalError掩盖ConnectionError。
- 用户交付：响应不存在与已有429响应分开处理，原始失败可诊断，进度输出按现有策略降级。
- 影响模块：contrib/discord.py:DiscordIO.message_id；contrib/telegram.py:TelegramIO.message_id。
- 兼容边界：不新增真实消息或凭据需求；保持成功/限流流程，测试只用模拟Session。
- 正常验收：响应前ConnectionError不会再被未绑定变量替代，成功响应仍缓存message_id。
- 边界／错误验收：429、坏JSON、缺id、HTTP错误、重入与初始化失败后的线程池清理覆盖。
- 原生回归：新增离线可选组件回归；tests/tests_contrib.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．as_completed接纳无长度任务生成器（修复）

- 来源／实际场景：[上游#1811](https://github.com/tqdm/tqdm/issues/1811)；Python3.12标准库对照。
- 原版现状：wrapper强制len(fs)抛TypeError，标准库可消费相同生成器。
- 用户交付：仅在可取得长度时推断total，生成器保持单次消费并用未知总量进度。
- 影响模块：asyncio.py:tqdm_asyncio.as_completed。
- 兼容边界：显式total优先；不为统计预先无界list化；各Python版本以标准库支持范围为准。
- 正常验收：三个tasks生成器全部得到结果，列表和显式total输出保持。
- 边界／错误验收：空/重复任务、timeout、创建异常、取消及generator.close不泄漏未await协程。
- 原生回归：tests/tests_asyncio.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．空DataFrame进度apply与Pandas一致（修复）

- 来源／实际场景：[上游#1810](https://github.com/tqdm/tqdm/issues/1810)空形状分支；实际DataFrame(0,2)。
- 原版现状：df.size // df.shape[axis]发生0除，原生apply成功。
- 用户交付：按轴形状推断需调用数量并保留空DataFrame原生apply结果/调用约定。
- 影响模块：std.py:tqdm.pandas/inner_generator总量推断。
- 兼容边界：Series/groupby/rolling逻辑保持；不手工伪造Pandas结果或跳过它可能执行的推断调用。
- 正常验收：0行2列和2行0列对相应axis与原生结果一致，不除零。
- 边界／错误验收：全空、轴别名/非法轴、用户函数异常与明确total=0均正确收尾。
- 原生回归：tests/tests_pandas.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．Pandas登记配置可重复使用（修复）

- 来源／实际场景：[上游#1810](https://github.com/tqdm/tqdm/issues/1810)共享total分支；连续Series调用。
- 原版现状：配置total=123首个条为123，第二个变4，因为闭包dict.pop。
- 用户交付：每次调用从不变登记配置读取total，直到再次tqdm.pandas显式更新。
- 影响模块：std.py:tqdm.pandas的tqdm_kwargs与inner。
- 兼容边界：保留deprecated_t单次对象的既有特殊语义；各次bar实例仍独立。
- 正常验收：连续两次/交错类型调用均沿用123，重新登记后使用新配置。
- 边界／错误验收：total=None/0、并发调用、异常首次调用及其他参数不被原调用修改。
- 原生回归：tests/tests_pandas.py:test_pandas_setup。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．DataFrame.map按元素计量进度（修复）

- 来源／实际场景：[上游#1798](https://github.com/tqdm/tqdm/issues/1798)；2列3行map实测。
- 原版现状：实际处理6元素但bar.total/n为2/2；上游测试目前也错误断言列数。
- 用户交付：元素map总数df.size，持续更新到所有元素完成，返回结果与Pandas不变。
- 影响模块：std.py:tqdm.pandas map总数分支。
- 兼容边界：Series.map仍按长度；DataFrame.apply仍按轴，不能全局改成size。
- 正常验收：2×3表调用6次，结束6/6，正常返回每格加一。
- 边界／错误验收：空表、na_action=ignore带缺失、异常和显式total覆盖策略明确；修正原生错误预期。
- 原生回归：tests/tests_pandas.py:test_pandas_data_frame。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．不登记Pandas不存在的GroupBy.map（修复）

- 来源／实际场景：[上游#1803](https://github.com/tqdm/tqdm/issues/1803)；真实GroupBy无map却有progress_map。
- 原版现状：调用虚假progress_map先建条再AttributeError，接口误导用户。
- 用户交付：按所支持Pandas能力登记progress_*；不为不存在map假造同名可用API，提供明确替代提示。
- 影响模块：std.py:tqdm.pandas注册GroupBy部分。
- 兼容边界：原本有效Series/DataFrame.map和GroupBy.apply保持；是否保留弃用shim需明确，不能悄悄改变为apply。
- 正常验收：真实有map的类型继续正常；无map的groupby不暴露伪可用方法或明确抛带替代的错误。
- 边界／错误验收：重复登记遗留属性清理、未来Pandas真有map、Series/DataFrameGroupBy和子类边界覆盖。
- 原生回归：tests/tests_pandas.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 13．进程分块按完成元素数更新（修复）

- 来源／实际场景：[上游#1791](https://github.com/tqdm/tqdm/issues/1791)；2进程11项chunksize4。
- 原版现状：返回11个正确结果，但每Future加1使进度3/11。
- 用户交付：根据真实完成chunk的元素数量累计，完成最后不足整块时也精确。
- 影响模块：contrib/concurrent.py:_executor_map/process_map回调。
- 兼容边界：保留结果顺序与完成时更新，thread/interpreter逐项不乘chunksize；不得回调里重复执行fn。
- 正常验收：11项分4/4/3块最终11/11，chunksize1保持。
- 边界／错误验收：空输入、多个不同长度iterable、异常chunk、取消/timeout、动态miniters与回调线程同步。
- 原生回归：tests/tests_concurrent.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．并发锁上下文异常也恢复（修复）

- 来源／实际场景：contrib/concurrent.py:ensure_lock缺finally；实际with抛RuntimeError。
- 原版现状：退出后tqdm.get_lock仍为临时锁，污染后续进度。
- 用户交付：用finally恢复原锁或撤销仅本次创建的类属性，原业务异常继续传播。
- 影响模块：contrib/concurrent.py:ensure_lock及调用者。
- 兼容边界：正常路径保持；不关闭调用方持有的锁，不跨类恢复到错误属性。
- 正常验收：正常与抛错退出均恢复原对象，后续条可更新。
- 边界／错误验收：原无_lock、嵌套、继承类、Pool初始化失败和恢复时外部接管规则明确。
- 原生回归：tests/tests_concurrent.py；tests/tests_rlock.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．Telegram删除请求使用格式化目标（修复）

- 来源／实际场景：contrib/telegram.py:TelegramIO.delete；假submit捕获真实传参。
- 原版现状：目标是字面{self.API}{self.token}/deleteMessage。
- 用户交付：使用实例API与合成token构造正确删除目标，并保留message_id/chat_id。
- 影响模块：contrib/telegram.py:TelegramIO.delete。
- 兼容边界：测试仅假Session，无真实发送；构造错误与HTTP失败按适配器现有策略处理。
- 正常验收：合成对象得到预期endpoint和正确data，未来集成测试无需真实token。
- 边界／错误验收：自定义API尾斜杠、缺message_id、submit抛错及leave=False触发删除不隐藏主要错误。
- 原生回归：新增离线Telegram回归；tests/tests_contrib.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．组合字符和ZWJ采用簇宽裁剪（增强）

- 来源／实际场景：utils.py明确TODO考虑wcswidth；实测e+音调计2、ZWJ开发者计5，wcwidth参考1/2。
- 原版现状：按码点east_asian_width累加，裁1列会从é丢掉音调。
- 用户交付：增加明确的终端宽度/簇处理策略，裁剪不拆组合簇，参考版本可冻结。
- 影响模块：utils.py:_text_width/disp_trim；std.py布局。
- 兼容边界：不声称所有字体/终端一致；如引入wcwidth须固定依赖并记录成本；ANSI/OSC结构保持。
- 正常验收：参考策略下é宽1、👩‍💻宽2，窄裁剪保留完整簇或整个省略。
- 边界／错误验收：VS15/VS16、旗帜、零宽、孤立组合符、CJK及颜色/超链接混合不拆控制区。
- 原生回归：tests/tests_utils.py；tests/tests_tqdm.py。
- 实际功能依赖：02。

### 17．布尔环境覆盖解析False和0（修复）

- 来源／实际场景：utils.py:envwrap回退；四个值真实装饰器观察。
- 原版现状：False/0/True/1均bool(str)=True，无法用环境明确关闭True选项。
- 用户交付：为布尔默认/注解使用确定词法解析，False/0与True/1对应布尔值。
- 影响模块：utils.py:envwrap；std.py构造环境覆盖。
- 兼容边界：显式调用参数仍优先；外部envwrap安装路径另做兼容，不默默改变数值/字符串参数。
- 正常验收：环境False/0关闭、True/1开启，实际TQDM_DISABLE同样可恢复显示。
- 边界／错误验收：空字符串、大小写、yes/no和非法值策略明确；import时读取语义、partialmethod和Optional类型不回退成真值。
- 原生回归：tests/tests_utils.py:test_envwrap；tests/tests_tqdm.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．对外部来源文本提供转义策略（增强）

- 来源／实际场景：[上游#1864](https://github.com/tqdm/tqdm/issues/1864)；合成desc/write控制码原样入StringIO。
- 原版现状：filename等字符串中的CSI/OSC/C0原样输出，无统一用户文本处理钩子。
- 用户交付：增加显式文本策略/escape回调作用于desc/postfix/write，允许显示可见转义而保留库自身渲染控制码。
- 影响模块：std.py:用户文本入口与write；utils.py文本策略。
- 兼容边界：默认兼容现有彩色/超链接用途；仅清理用户内容，不清除库自己的CR/光标移动；不渲染合成攻击到真实终端。
- 正常验收：opt-in后合成ESC/OSC表现为可见文字，普通中文文件名不变。
- 边界／错误验收：换行/tab、BEL/C1、已带SGR/OSC8信任策略、错误回调和非TTY输出明确。
- 原生回归：tests/tests_tqdm.py；tests/tests_utils.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．可选计时源与暂停时间口径（增强）

- 来源／实际场景：[上游#1748](https://github.com/tqdm/tqdm/issues/1748)；实际_bar._time为time且无clock参数。
- 原版现状：时钟硬编码墙钟，CPU密集任务无法选择process_time，reset不改变计时源。
- 用户交付：提供显式计时器选择/注入，统一初始化、刷新、reset及暂停语义，显示口径可解释。
- 影响模块：std.py:__init__/update/reset/format_dict；_monitor兼容。
- 兼容边界：默认墙钟保持；CPU时间不含IO且多核可叠加，必须明确，不能仅替换_time而沿用旧start_t。
- 正常验收：受控墙钟/CPU钟序列产生对应elapsed/rate，reset后同一口径不跳变。
- 边界／错误验收：倒退/零增量、暂停恢复、监控线程调度与CPU耗时分开、异常时钟返回有明确处理。
- 原生回归：tests/tests_tqdm.py；tests/tests_synchronisation.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．无句柄调用方可更新临时状态行（增强）

- 来源／实际场景：[上游#1794](https://github.com/tqdm/tqdm/issues/1794)；write固定换行，set_postfix_str需self。
- 原版现状：回调/底层库只能write不断滚动，无法更新一个短暂共享状态。
- 用户交付：新增显式临时状态上下文/类级入口，在指定流和所属进度区域内替换状态，后续更新可清除。
- 影响模块：std.py:external_write_mode/write/display；多实例布局。
- 兼容边界：保留write永久日志语义；不隐式选择任意实例或改它的postfix，输出流/归属明确。
- 正常验收：无bar句柄的回调连续设置状态只占一行，进度继续时按策略清除。
- 边界／错误验收：多条/多流、跨线程、嵌套所有权、最后一条结束、非TTY只输出约定最终状态。
- 原生回归：tests/tests_tqdm.py；tests/tests_contrib_logging.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

已有异步迭代/gather(return_exceptions)、多条position进度、process/thread/interpreter_map、动态宽度、reset(total)/initial续跑、单位/逆速率、format_dict、时间完成点{eta}、日志重定向和callback IO。上游#1801的无长度输入min空序列已在该commit修复，不计BUG；#1745请求的完成时钟已可用bar_format显示，不重复增强。外部envwrap可作为布尔解析的替代，但本次实际未安装，复现的是utils内置回退。测试/格式化迁移、CI发布设置和新动画不计步。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
