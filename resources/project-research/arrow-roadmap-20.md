# Arrow 二十步迭代研究路线

固定[arrow-py/arrow@2224255c4acc594d734cef0bbc83360452a67983](https://github.com/arrow-py/arrow/tree/2224255c4acc594d734cef0bbc83360452a67983)；20步尚未实施，正常/边界验收均为未来目标。01/02/03/05/06为原版实证问题，其余15步为增强或显式策略，不声称上游承诺。
既有ZoneInfo、shift(check_imaginary)、Arrow range输入、only_distance、格式列表及微秒舍入已核实，不重复作为新能力；fraction和负号归同一dehumanize数值语法交付。

## 01．dehumanize把完整数值作为一个时间量

- **类型／来源和场景**：bug_fix；[来源](https://github.com/arrow-py/arrow/issues/1341)；用户输入1.5 hours ago不应被解释成5小时前，非法负号也不能悄悄变正。
- **原版现状／替代**：实跑1.5 hours ago从午夜减5小时；in -2 days反而加2天；数字正则只识别整数片段。
- **交付与模块**：统一数值词法，接收有明确精度的小数；负数与in/ago方向矛盾时明确拒绝或按文档策略处理。；`arrow/arrow.py`、`arrow/locales.py`。
- **兼容边界**：同一数字语法缺陷合并小数与符号症状；分数月/年默认拒绝不自定30天。
- **正常验收**：1.5小时得到前日22:30，0.5天得到前日12:00，in -2 days不再静默反向。
- **异常／边界验收**：负零、逗号小数语言、复合单位、重复单位、超微秒精度和不能识别的完整数字。
- **原生回归**：`tests/test_arrow.py`、`tests/test_locales.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 02．时区表达式完整匹配并验证分量

- **类型／来源和场景**：bug_fix；[来源](https://github.com/arrow-py/arrow/issues/1294)；配置值+03:00.34应报告错误，不能忽略尾随文本。
- **原版现状／替代**：TzinfoParser.parse实跑接受+03:00.34并返回+03:00；正则没有结束锚。
- **交付与模块**：固定偏移使用完整匹配并检查小时/分钟；格式错误统一为ParserError。；`arrow/parser.py`。
- **兼容边界**：UTC/local/IANA ZoneInfo保持；现有受支持(UTC)外壳格式明确；不自动猜错字。
- **正常验收**：+03:00.34、+03:99被拒绝，合法+03:00和-0330保持。
- **异常／边界验收**：空值、正负零、24小时边界、括号、空白与IANA名误落偏移分支。
- **原生回归**：`tests/test_parser.py`、`tests/test_factory.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 03．精确月区间连续覆盖整个输入范围

- **类型／来源和场景**：bug_fix；[来源](https://github.com/arrow-py/arrow/issues/1185)；从1月31日起按月切分账期时不能漏掉3月28日至30日。
- **原版现状／替代**：实跑前两段到2月27/3月27，第三段却从3月31起；range恢复原始日而span沿截断日推进。
- **交付与模块**：exact月/季度/年区间的后段从上一段终点边界连续推进，消除恢复原始日造成的缝隙。；`arrow/arrow.py`。
- **兼容边界**：普通range原始日恢复契约保持；只调整精确区间切分；bounds微秒开闭语义一致。
- **正常验收**：1月31日至5月1日的输出区间无空隙无重叠且整体恰好覆盖输入。
- **异常／边界验收**：闰年2月、季度/年、limit、四种bounds、DST边界、start=end和倒序输入。
- **原生回归**：`tests/test_arrow.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 04．humanize可选择按日历逐单位分解

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/948)；同一锚点加一年四月两天后，产品希望展示准确日历分量而非固定平均月秒数。
- **原版现状／替代**：实跑输出一年四个月零天六小时两秒；多单位用_SECS_MAP平均年/月逐次取模。
- **交付与模块**：新增opt-in calendar分解策略，按锚点逐单位推进并从剩余差额产生后续单位。；`arrow/arrow.py`。
- **兼容边界**：现有近似策略保持；不把所有月份当固定秒数；明确负方向和月底截断。
- **正常验收**：2017-01-01到2018-05-03 06:00:02按策略展示1年4月2天6小时2秒。
- **异常／边界验收**：月底、闰年、DST、负差、未选月份/天数、quarter和单位顺序标准化。
- **原生回归**：`tests/test_arrow.py`、`tests/test_locales.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 05．午夜DST跳变前一天的ceil保持原日期

- **类型／来源和场景**：bug_fix；[来源](https://github.com/arrow-py/arrow/issues/1124)；智利午夜夏令时跳变前一天求日终，必须仍在该日。
- **原版现状／替代**：已实跑9月10日ceil(day)得到9月11日01:59:59.999999。
- **交付与模块**：日界构造与减最小单位时统一处理不存在的午夜，返回当天最后可表示时刻。；`arrow/arrow.py`。
- **兼容边界**：继续支持shift默认imaginary解析；不通过全局关闭检查来修ceil；实际时区数据版本保留。
- **正常验收**：样例结果为2022-09-10 23:59:59.999999-04:00且日期不变。
- **异常／边界验收**：普通23/25小时日、半小时/整日跳变、其他frame、floor/span和极值日期。
- **原生回归**：`tests/test_arrow.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 06．数字星期d解析与格式化一致

- **类型／来源和场景**：bug_fix；[来源](https://github.com/arrow-py/arrow/issues/1072)；格式d读入3后，输出dddd应是Wednesday。
- **原版现状／替代**：实跑arrow.get(3,d)为公元1年1月1日Monday；_parse_token没有d分支。
- **交付与模块**：实现数字星期1..7到day_of_week映射，复用已有命名星期的锚点规则。；`arrow/parser.py`、`arrow/formatter.py`。
- **兼容边界**：格式化现有d=ISO星期编号保持；已提供完整年月日时对冲突星期的行为明确。
- **正常验收**：3格式d转成星期三；1到7逐个解析后format(d)往返。
- **异常／边界验收**：0/8拒绝、带年/月、完整日期冲突、前导零、locale与命名星期对照。
- **原生回归**：`tests/test_parser.py`、`tests/test_formatter.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 07．显式严格格式匹配模式

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1084)；表单要求整串符合指定格式，并可要求M/D等token精确宽度。
- **原版现状／替代**：DateTimeParser使用search；实跑prefix/suffix文本仍成功；单M也允许两位月，当前属宽松语义。
- **交付与模块**：增加strict匹配策略，选择全串和精确token宽度规则，保留宽松extract默认。；`arrow/parser.py`、`arrow/factory.py`。
- **兼容边界**：不把现有宽松解析称缺陷；literal、normalize_whitespace和ISO默认流程分别定义。
- **正常验收**：严格模式拒绝prefix日期suffix和宽度不符输入，合法格式仍成功。
- **异常／边界验收**：多格式列表、空白归一化、文字括号、时区token、Unicode数字和错误位置。
- **原生回归**：`tests/test_parser.py`、`tests/test_factory.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 08．解析报告返回匹配片段与字符位置

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/897)；离线日志编辑器取出日期同时保留同一行其余文本。
- **原版现状／替代**：parse只返回datetime，匹配Match对象在局部变量中被丢弃；调用方可自行写regex。
- **交付与模块**：新增独立parse_match报告，含日期、选中的format、span、matched text与其余文本。；`arrow/parser.py`、`arrow/factory.py`。
- **兼容边界**：原返回类型保持；原字符串与normalize_whitespace后的索引必须区分，不伪报原索引。
- **正常验收**：解析prefix 2026-01-02 suffix返回准确片段和字符范围，剩余文本不丢。
- **异常／边界验收**：多个日期取首个/迭代策略明确、Unicode、重复格式、无匹配、可选token和空匹配。
- **原生回归**：`tests/test_parser.py`、`tests/test_factory.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 09．只对缺时区输入应用默认时区

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1293)；导入记录缺时区时用项目默认，但显式-0800不能被默认Eastern替换。
- **原版现状／替代**：tzinfo参数会覆盖已解析偏移；样例实跑00:00-0800变00:00-0500，API目前就是replace语义。
- **交付与模块**：新增default_tz参数/工厂策略，仅输入未声明tz时使用，保留tzinfo显式覆盖。；`arrow/factory.py`、`arrow/parser.py`。
- **兼容边界**：无法仅靠结果为UTC判断缺时区，解析阶段传递显式tz标记；既有get不变。
- **正常验收**：无偏移字符串用默认Eastern，显式UTC和-0800均保持原偏移。
- **异常／边界验收**：datetime输入、时间戳、local、ZoneInfo、默认与覆盖同时给出时拒绝或明确优先级。
- **原生回归**：`tests/test_factory.py`、`tests/test_api.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 10．humanize可以强制数字一

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1158)；仪表盘希望1 hour与2 hours统一用数字，避免a/an词。
- **原版现状／替代**：humanize numeric=True实跑TypeError；locale单数常量为a/an，可应用自定义locale替代。
- **交付与模块**：新增明确numeric策略与locale数词模板，单数用1并保留语言变格。；`arrow/arrow.py`、`arrow/locales.py`。
- **兼容边界**：默认自然语言保持；不对成品英文字符串replace以免破坏其他语言。
- **正常验收**：英语1 hour/1 minute和复合单位均数字化，默认仍an hour。
- **异常／边界验收**：负差、only_distance、无数字词语言、复数规则及零值。
- **原生回归**：`tests/test_arrow.py`、`tests/test_locales.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 11．humanize提供简短单位风格

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1001)；空间有限的本地看板展示2h 34m 56s。
- **原版现状／替代**：brief=True实跑TypeError；only_distance只省方向文字，不缩短单位。
- **交付与模块**：增加可选short style与locale短单位数据，复用相同单位分解。；`arrow/arrow.py`、`arrow/locales.py`。
- **兼容边界**：默认长文本保持；大小写m月/分钟需明确；不保证所有locale自动有同一缩写。
- **正常验收**：已声明英语短风格输出2h 34m 56s，方向前后缀按选项一致。
- **异常／边界验收**：缺短翻译的回退、单数、单位碰撞、zero、最大单位数和Unicode。
- **原生回归**：`tests/test_arrow.py`、`tests/test_locales.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 12．humanize可以限制输出单位数量

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1013)；倒计时选择小时分钟秒粒度，但卡片最多展示两个单位。
- **原版现状／替代**：max_units参数实跑TypeError；可先手动选择granularity但需调用方预先计算哪些单位可见。
- **交付与模块**：新增max_units对已选粒度结果按重要性截断，明确零单位计数策略。；`arrow/arrow.py`。
- **兼容边界**：默认不限制；此功能只裁剪既有分解结果，不隐式舍入或更改总时差。
- **正常验收**：2小时34分56秒配max_units2只输出小时分钟；1只输出小时。
- **异常／边界验收**：0/负数参数、全零分量、跳选hour/second、超过实际数量与only_distance。
- **原生回归**：`tests/test_arrow.py`、`tests/test_locales.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 13．冰岛语支持零值单位的人性化

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1011)；等时刻按hour/minute粒度展示时，冰岛语界面也应返回可用文本。
- **原版现状／替代**：实跑locale=is、多粒度零差ValueError；IcelandicLocale明确未实现zero映射。
- **交付与模块**：补齐冰岛语零值单位及方向/距离行为，统一正负零与多粒度调用。；`arrow/locales.py`。
- **兼容边界**：使用经确认的语言表达，不将未来格随意当零格；保持非零既有语法。
- **正常验收**：同一时刻的hour/minute/second和多单位可以展示零值，only_distance不带错误方向。
- **异常／边界验收**：截断后为零的小差值、负零、单数/复数以及所有本locale支持粒度。
- **原生回归**：`tests/test_locales.py`、`tests/test_arrow.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 14．可选离线CLDR本地化数据提供方

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1081)；应用希望升级月份/星期等本地化数据，而不等待Arrow全部发布。
- **原版现状／替代**：locales为源码类注册表，没有provider或CLDR适配；可自定义Locale子类。
- **交付与模块**：增加可选provider协议与受限CLDR/Babel离线适配，先覆盖月份/星期/相对时间声明范围。；`arrow/locales.py`、`arrow/formatter.py`、`arrow/parser.py`。
- **兼容边界**：现有Locale默认优先级明确；不承诺全部CLDR日历/时区功能；适配数据版本与许可独立记录。
- **正常验收**：指定冻结provider后某locale月名按数据返回，卸载可选包时原有locale照常工作。
- **异常／边界验收**：地区回退、数据缺项、冲突locale、未知版本、线程并发与缓存更新。
- **原生回归**：`tests/test_locales.py`、`tests/test_formatter.py`、`tests/test_parser.py`。
- **实际依赖／步骤依赖**：计划可选Babel/CLDR离线数据适配；本次未安装或执行该未来provider，实施前需固定数据/包版本及许可。现有运行依赖不变。；无。

## 15．Excel序列日期的显式转换入口

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/977)；离线表格导入同列包含Excel1900或1904日期系统的数值。
- **原版现状／替代**：Arrow没有from_excel/serial日期入口；可以使用xlrd或应用自行转换。
- **交付与模块**：新增明确from_excel/to_excel接口，必须指定日期系统并保留日内小数精度。；`arrow/arrow.py`、`arrow/factory.py`。
- **兼容边界**：不把普通数值get从Unix时间戳改为Excel；对虚构1900-02-29明确错误/哨兵策略。
- **正常验收**：同一真实日期在1900/1904模式正确互转，.5表示同日中午。
- **异常／边界验收**：序号0/59/60/61、负值、微秒舍入、时区默认和超出datetime范围。
- **原生回归**：`tests/test_arrow.py`、`tests/test_factory.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 16．GPS时间与UTC转换采用显式闰秒表

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1109)；科学离线记录包含GPS秒，需要可复核地转换到UTC。
- **原版现状／替代**：Arrow没有GPS入口；可用外部gpstime/astropy，普通Unix timestamp不能代替GPS。
- **交付与模块**：新增可选GPS转换模块，接收冻结闰秒表及有效区间，明确GPS epoch与UTC映射。；`arrow/arrow.py`、`arrow/factory.py`。
- **兼容边界**：不内置未经维护的永久闰秒常数，不在线拉取；datetime不能表示闰秒标签时明确返回策略。
- **正常验收**：GPS epoch零映射1980-01-06 UTC，给定测试表的已知时刻双向往返。
- **异常／边界验收**：表有效期外、负GPS秒、周计数rollover须显式参数、闰秒边界歧义与小数精度。
- **原生回归**：`tests/test_arrow.py`、`tests/test_factory.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 17．提供明确的实际经过时间运算

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1136)；夏令时回拨相邻两个Unix秒的差应在elapsed模式下是1秒。
- **原版现状／替代**：已实跑普通减法为-3599秒、timestamp差为1秒；前者遵循Python相同时区wall-time语义。
- **交付与模块**：新增elapsed差值/精确时间平移入口，以UTC时间线运算后转换回原时区。；`arrow/arrow.py`。
- **兼容边界**：普通运算符和shift日历语义保持；月份/年不是固定实际时长，不允许隐式参与。
- **正常验收**：相邻Unix秒elapsed差1；精确加1秒跨回拨落到下一个真实时刻且fold正确。
- **异常／边界验收**：naive输入、不同tz、UTC、春季缺时刻、负时长与极值溢出。
- **原生回归**：`tests/test_arrow.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 18．解析器可显式注册时区缩写映射

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1065)；业务数据的CST确定为上海时区，需要由调用方声明而非全局猜测。
- **原版现状／替代**：TzinfoParser只接一个字符串，ZZZ由ZoneInfo名字解析；不能传本次缩写映射。
- **交付与模块**：增加可选别名resolver参数，先按用户声明映射到固定偏移或IANA zone，再走既有解析。；`arrow/parser.py`、`arrow/factory.py`。
- **兼容边界**：不构建全球唯一缩写表；同一缩写有歧义时必须显式配置；不覆盖UTC保留名除非清楚规则。
- **正常验收**：CST配置Asia/Shanghai后正确+08:00；另一个工厂配置America/Chicago不串值。
- **异常／边界验收**：未知缩写、季节性offset、大小写、resolver异常、缓存按配置隔离和format来源。
- **原生回归**：`tests/test_parser.py`、`tests/test_factory.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

## 19．显式通配片段token用于部分日期提取

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/976)；文本14-2010的前段不是合法月，但业务只需要后面的年。
- **原版现状／替代**：格式**-YYYY实跑不匹配；可自己regex或预切文本。
- **交付与模块**：增加明确命名的skip/wildcard格式token，跳过声明片段并只构造实际要求字段。；`arrow/parser.py`。
- **兼容边界**：不把错误月数字偷偷当合法月；通配默认只匹配界定片段，不改变现有literal星号。
- **正常验收**：skip前段后year得到2010，报告注明该段被忽略。
- **异常／边界验收**：空片段、分隔符冲突、多个wildcard、Unicode、缺年、严格模式与匹配报告一致。
- **原生回归**：`tests/test_parser.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；[8]。

## 20．中文humanize可选择统一数词风格

- **类型／来源和场景**：enhancement；[来源](https://github.com/arrow-py/arrow/issues/1009)；中文界面不希望一秒与2天混合数词风格，可选择阿拉伯数字或中文数词。
- **原版现状／替代**：实跑两天距离输出2天，而单数模板可为一；没有统一数词选项。
- **交付与模块**：在中文locale添加明确number_style并统一单复数量，使用限定范围的数词格式器。；`arrow/arrow.py`、`arrow/locales.py`。
- **兼容边界**：默认输出保持；不全局替换日期字符串数字；不影响英文numeric选项的语义。
- **正常验收**：简体中文风格2天输出两天、20天输出二十天；数字风格得到1秒/2天，复合单位一致。
- **异常／边界验收**：0/10/11/20/101、大数范围、负方向、only_distance、地区变体及缺数词数据。
- **原生回归**：`tests/test_locales.py`、`tests/test_arrow.py`。
- **实际依赖／步骤依赖**：沿用python-dateutil与tzdata和Python标准库；当前依赖精确版本已冻结，无额外服务。；无。

未来在同一真实源码累计修改，每步含实现/测试/文档/失败修复。控制端冻结验收并检查加载候选路径、实际日期/文本/区间输出，回归原生含coverage门槛和此前接受能力；研究尚未完成这些新增验收。
