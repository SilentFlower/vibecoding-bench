# python-dateutil 二十步迭代研究路线

固定[dateutil/dateutil@68994217fbe253835989e7c1e3eeef5c653088d1](https://github.com/dateutil/dateutil/tree/68994217fbe253835989e7c1e3eeef5c653088d1)。01—06为本提交已复现缺陷，07—20为新增能力或显式兼容策略提案；全部未实施，未由上游承诺。当前只验证原版行为，验收是未来交付目标。
没有把同源精度问题按parse/isoparse拆步；现有rrule.replace、weekday序数、datetime_exists/resolve_imaginary、tzfile.key、TZPATH和毫秒转微秒的手工替代均明确保留。

## 01．复发规则正确展开HTAB续行

- **类型／来源与场景**：bug_fix；[来源](https://github.com/dateutil/dateutil/issues/1591)；导入日历提供方使用制表符续行的两日会议规则。
- **原版现状／替代方式**：RRULE的CRLF+HTAB折行实跑ValueError；_parse_rfc仅认空格。
- **交付与模块**：同一展开器按RFC接收空格与HTAB续行，复用在规则与tzical文本。；`src/dateutil/rrule.py`、`src/dateutil/tz/tz.py`。
- **兼容边界**：只移除规范的一个续行前缀；不无条件strip整行改变值。
- **正常验收**：空格和HTAB折行都产生1月1/2日两个实例。
- **异常／边界验收**：混合换行、连续折行、空行、首行缩进和时区组件折行。
- **原生回归**：`tests/test_rrule.py`、`tests/test_tz.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 02．混合普通与序数BYDAY按并集选择

- **类型／来源与场景**：bug_fix；[来源](https://github.com/dateutil/dateutil/issues/1588)；一个月的每周五加首个周五应等价于所有周五，而非每月仅第一个周五。
- **原版现状／替代方式**：FR,1FR实跑返回五个月各首个周五；_iter独立拒绝_byweekday与nwdaymask。
- **交付与模块**：将同一BYDAY列表普通与序数分支合并成选择并集，再与其他BY条件取交。；`src/dateutil/rrule.py`。
- **兼容边界**：不同BY属性仍取交；保留COUNT/BYSETPOS和日历合法性过滤。
- **正常验收**：FR,1FR得到1月5/12/19/26与2月2日；MO,1FR得到对应并集。
- **异常／边界验收**：YEARLY含BYMONTH、负序数、重复weekday、无普通分支、BYSETPOS和UNTIL。
- **原生回归**：`tests/test_rrule.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 03．普通解析器拒绝非法时区分量

- **类型／来源与场景**：bug_fix；[来源](https://github.com/dateutil/dateutil/issues/1508)；日志日期含+00:60时应报告输入错误，不能静默变成+01:00。
- **原版现状／替代方式**：parse(+0060)实跑得到+01:00；_parser数字时区分支未校验分钟和小时。
- **交付与模块**：在构建偏移前验证分量及总范围，统一抛ParserError并保留cause。；`src/dateutil/parser/_parser.py`、`src/dateutil/tz/tz.py`。
- **兼容边界**：正常短小时/HHMM/HH:MM格式保持；UTC/GMT反号的已知语义不随本修复改写。
- **正常验收**：+0060、+0560、+2400立即被拒绝；合法+0530得到5.5小时。
- **异常／边界验收**：负偏移、边界23:59、ignoretz明确行为、用户tzinfos和后续isoformat可用性。
- **原生回归**：`tests/test_parser.py`、`tests/test_tz.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 04．复发生成跳过不存在的本地时间

- **类型／来源与场景**：bug_fix；[来源](https://github.com/dateutil/dateutil/issues/1425)；每日凌晨2点半提醒跨夏令时跳变，缺失的本地时刻不能占用COUNT。
- **原版现状／替代方式**：实跑纽约2025-03-09 02:30仍被生成，datetime_exists为False。
- **交付与模块**：在输出候选和递减count前检查带时区的本地时间存在性，默认跳过不存在实例。；`src/dateutil/rrule.py`、`src/dateutil/tz/tz.py`。
- **兼容边界**：naive规则不额外附时区；重复时刻的fold选择另行保持既有契约，不在此拆一步。
- **正常验收**：count5从3月7起输出7/8/10/11/12日，全部datetime_exists为True。
- **异常／边界验收**：BYSETPOS路径、UNTIL边界、非整小时跳变、tzinfo实现限制及计数/缓存一致。
- **原生回归**：`tests/test_rrule.py`、`tests/test_tz.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 05．ISO周日期验证该年是否具有第53周

- **类型／来源与场景**：bug_fix；[来源](https://github.com/dateutil/dateutil/issues/1236)；导入2021-W53-1应失败，不能滚到下一ISO年。
- **原版现状／替代方式**：isoparse实跑返回2022-01-03；_calculate_weekdate只检查week<54。
- **交付与模块**：按ISO年实际周数校验，并确认计算结果的isocalendar年/周符合输入。；`src/dateutil/parser/isoparser.py`。
- **兼容边界**：有效跨Gregorian年边界的ISO周仍合法；不简单禁止全部53周。
- **正常验收**：2021-W53拒绝，2020-W53合法且星期正确。
- **异常／边界验收**：首末年份、基本/扩展格式、缺省weekday、day0/8和week00/54。
- **原生回归**：`tests/test_isoparser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 06．tzical容忍规范允许的X扩展属性

- **类型／来源与场景**：bug_fix；[来源](https://github.com/dateutil/dateutil/issues/1368)；本地VTIMEZONE附带X-LIC-LOCATION用于信息展示，不能因此无法读取时区。
- **原版现状／替代方式**：最小合法组件加X-LIC-LOCATION实跑unsupported property。
- **交付与模块**：按组件允许扩展属性并选择保留元信息或忽略，仍严格验证必需时区字段。；`src/dateutil/tz/tz.py`。
- **兼容边界**：未知非X标准属性继续按明确策略报错；不执行属性内容或访问TZURL。
- **正常验收**：同一VTIMEZONE加X属性后和不加时的offset/transition一致。
- **异常／边界验收**：组件内外X属性、带参数、重复值、大小写、缺失TZID/offset和错误BEGIN/END。
- **原生回归**：`tests/test_tz.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 07．带缓存的rrule和rruleset支持pickle往返

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1369)；应用保存已创建的会议规则到本地缓存，cache=True不应阻止规则序列化。
- **原版现状／替代方式**：pickle.dumps(cache=True规则)实跑TypeError thread.lock；cache=False或应用copyreg可替代。
- **交付与模块**：增加稳定状态序列化，只存规则定义和缓存策略，重建锁/迭代器而非序列化运行锁。；`src/dateutil/rrule.py`。
- **兼容边界**：不加载未受信pickle；不保证活动迭代器精确位置；旧可用pickle保持读取。
- **正常验收**：rrule和rruleset往返后查询相同日期，缓存开关保持且新锁独立。
- **异常／边界验收**：空/部分/完整缓存、多个包含排除规则、深拷贝、时区对象与旧状态版本。
- **原生回归**：`tests/test_rrule.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 08．解析结果可报告显式字段与默认字段

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1405)；January 2有月日但没有年，表单需要区别用户输入与默认补齐。
- **原版现状／替代方式**：parse只返回datetime或fuzzy跳过tokens；私有_result知道哪些字段为None，公开接口没有报告。
- **交付与模块**：新增独立解析报告，含datetime、显式/默认字段集合和可支持的token来源。；`src/dateutil/parser/_parser.py`、`src/dateutil/parser/__init__.py`。
- **兼容边界**：默认parse返回类型不变；不声称有唯一strptime格式；默认值相等也能区分来源。
- **正常验收**：January 2报告month/day显式而year默认，完整ISO字段全部显式。
- **异常／边界验收**：AM/PM、weekday调整、月底截断、fuzzy tokens、重复字段与timezone解析来源。
- **原生回归**：`tests/test_parser.py`、`tests/test_internals.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 09．日期顺序可选择严格模式

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1448)；只接收月/日/年的表单希望13/02/2024被拒绝，而非回退到日/月。
- **原版现状／替代方式**：dayfirst=False实跑仍将13/02解释为2月13日；当前dayfirst/yearfirst是偏好不是严格约束。
- **交付与模块**：新增opt-in顺序约束策略，在数字三元组解析时禁止违背声明顺序的回退。；`src/dateutil/parser/_parser.py`。
- **兼容边界**：保留现有宽松默认；明确命名月份和完整四位年格式的优先规则。
- **正常验收**：严格MDY拒绝13/02/2024、接受02/13/2024；默认模式保持当前结果。
- **异常／边界验收**：歧义01/02/03、YMD/DMY组合、两位年窗口、不同分隔符和fuzzy。
- **原生回归**：`tests/test_parser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 10．超微秒精度的显式舍入或拒绝策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1545)；输入0.1234567秒时，应用需要选择截断、舍入或拒绝，而非隐式丢精度。
- **原版现状／替代方式**：普通parse和isoparse实跑都得到123456微秒；二者同源需求合为一步，默认截断已有。
- **交付与模块**：统一可选precision策略，支持truncate/round/reject并处理秒/日进位。；`src/dateutil/parser/_parser.py`、`src/dateutil/parser/isoparser.py`。
- **兼容边界**：默认截断保持；datetime仍限微秒，不虚构纳秒存储；明确half-even或其他固定舍入模式。
- **正常验收**：round将.1234567转123457；reject对第7位拒绝；truncate仍123456。
- **异常／边界验收**：恰好半值、.9999999跨日、负号边界、逗号小数、时区与6位及更少位。
- **原生回归**：`tests/test_parser.py`、`tests/test_isoparser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 11．ISO时间支持小数小时和小数分钟

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/blob/68994217fbe253835989e7c1e3eeef5c653088d1/src/dateutil/parser/isoparser.py)；设备给出12.5或12:30.5来表达分数小时/分钟。
- **原版现状／替代方式**：isoparse(12.5)实跑ValueError；文档明确该ISO能力尚未实现。
- **交付与模块**：在最低已提供时间分量解释小数并换算下级分量，复用明确精度策略。；`src/dateutil/parser/isoparser.py`。
- **兼容边界**：不把点误当冒号分隔；完整秒小数保持；默认是否扩展接受集合须发布说明。
- **正常验收**：12.5得到12:30，12:30.5得到12:30:30。
- **异常／边界验收**：基本/扩展格式、逗号、24点边界、非法混合小数、过长精度和时区。
- **原生回归**：`tests/test_isoparser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；[10]。

## 12．ISO8601期间文本与relativedelta转换

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/854)；配置文件用P1M2DT3H表达一个月两天三小时的等待周期。
- **原版现状／替代方式**：公开parser没有期间入口，isoparse该字符串失败；可手动构造relativedelta或用外部isodate。
- **交付与模块**：新增独立duration解析/格式化入口，明确映射年/月和固定长度时间分量。；`src/dateutil/relativedelta.py`、`src/dateutil/parser/isoparser.py`。
- **兼容边界**：不把一个月换成固定30天；不改变isoparse日期入口；明确支持的符号/小数期间子集。
- **正常验收**：P1M2DT3H解析后加到固定锚点得到预期日历日期，规范格式可往返。
- **异常／边界验收**：零期间、负期间、周混合限制、月份与分钟区分、非法序列和小数月明确拒绝。
- **原生回归**：`tests/test_relativedelta.py`、`tests/test_isoparser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 13．relativedelta支持毫秒相对量与绝对量

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1175)；UI传42毫秒时不想在每处手工乘1000，也需要清楚的绝对毫秒替换。
- **原版现状／替代方式**：milliseconds参数实跑TypeError，当前可用microseconds=42000或timedelta。
- **交付与模块**：新增milliseconds/millisecond声明并与微秒统一规范化，明确同时声明时的冲突/顺序。；`src/dateutil/relativedelta.py`。
- **兼容边界**：现有微秒行为和normalized保持；毫秒是同一用户能力，不按相对/绝对拆两步。
- **正常验收**：milliseconds=42相加增加42000微秒，millisecond=42按契约替换对应部分。
- **异常／边界验收**：负数、跨秒、fractional值精度、绝对范围、与microsecond组合及乘除。
- **原生回归**：`tests/test_relativedelta.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 14．本地工作日历支持节假日和滚动规则

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1307)；交付日期需跳过周末和明确给定的节假日，并支持前推/后推到工作日。
- **原版现状／替代方式**：rrule已能按周一至周五加exdate，但没有统一的business calendar接口；可由调用方组合。
- **交付与模块**：新增轻量本地日历对象，声明weekmask和假日集合，提供is_business_day、roll、add_business_days。；`src/dateutil/rrule.py`、`src/dateutil/relativedelta.py`。
- **兼容边界**：不内置在线国家假日查询；时区/时间部分保留策略明确；与普通days不同语义。
- **正常验收**：给定周一假期，周五加1工作日到周二，前后滚动均可预测。
- **异常／边界验收**：全非工作日weekmask拒绝、负步长、同日零步、闰日、重复假日和date/datetime。
- **原生回归**：`tests/test_rrule.py`、`tests/test_relativedelta.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 15．RDATE支持TZID与DATE值参数

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/872)；日历导入一条带TZID的额外会议和一条全日日期。
- **原版现状／替代方式**：RDATE;TZID实跑ValueError；EXDATE和DTSTART已有_parse_date_value能力可复用。
- **交付与模块**：把RDATE的TZID/DATE-TIME/DATE处理接入公共日期值解析，明确全日值映射；PERIOD继续列为未支持。；`src/dateutil/rrule.py`。
- **兼容边界**：不宣称支持全部PERIOD；ignoretz/tzids/tzinfos按既有DTSTART/EXDATE契约传递。
- **正常验收**：巴黎TZID额外日期拥有正确offset，VALUE=DATE的全日日期按明确模式进入集合。
- **异常／边界验收**：多值、大小写TZID、未知TZID、重复参数、混合aware/naive、ignoretz与非法日期。
- **原生回归**：`tests/test_rrule.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 16．rruleset提供稳定的文本导出和往返

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/856)；含排除日期的会议日历保存为文本后应能重建，不能只有单条rrule可导出。
- **原版现状／替代方式**：str(rruleset())实跑对象地址；目前可私读_rrule/_rdate/_exrule/_exdate手工拼文本。
- **交付与模块**：新增显式to_ical或等价序列化，完整输出包含/排除规则日期和必需时区标识。；`src/dateutil/rrule.py`。
- **兼容边界**：不改变默认object repr除非明确；时区无法恢复时要求调用方resolver；输出只描述规则不展开无穷日期。
- **正常验收**：含一个规则、一条RDATE和EXDATE的集合导出再rrulestr后在固定窗口结果相同。
- **异常／边界验收**：空集合、多个规则、UTC/TZID、长行折行、日期去重、未知时区与无限规则。
- **原生回归**：`tests/test_rrule.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；[15]。

## 17．公开不可变的复发规则定义视图

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1216)；日历编辑器读取freq/interval/BY条件而不依赖私有属性。
- **原版现状／替代方式**：rrule有replace及str，但没有公开parts或freq/interval定义视图；_original_rule为内部数据。
- **交付与模块**：新增只读RuleParts/属性视图，区分显式输入和从DTSTART推导的有效条件。；`src/dateutil/rrule.py`。
- **兼容边界**：不允许修改视图绕过缓存失效；replace仍创建新规则；不把查询方法count误当定义count。
- **正常验收**：查看MONTHLY interval2返回准确字段和显式BYDAY，视图不改变枚举结果。
- **异常／边界验收**：默认dtstart、until/count、weekday序数、推导BYMONTHDAY、copy和不可变嵌套值。
- **原生回归**：`tests/test_rrule.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 18．isoparse对已允许的不完整日期支持default

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1364)；只给2026-02时希望按指定锚点补到月底而不是总为1日。
- **原版现状／替代方式**：isoparse default参数实跑TypeError，当前不完整日期取最低值；普通parse已有default。
- **交付与模块**：增加明确default参数，对已允许的不完整ISO形式补缺字段并按月长截断日。；`src/dateutil/parser/isoparser.py`。
- **兼容边界**：默认最低值保持；不能借default放行ISO原本禁止的不完整日期加时间组合。
- **正常验收**：2026-02加day31默认补到2月28日；完整日期不被默认日期覆盖。
- **异常／边界验收**：闰月、year-only、时区默认策略、24点跨日、超范围默认和缺失/显式字段区分。
- **原生回归**：`tests/test_isoparser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 19．提供有序ChainParser与匹配来源

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1153)；应用先尝试已知格式，再ISO，最后普通解析，并需知道采用哪一个。
- **原版现状／替代方式**：parser公开没有ChainParser；可应用for循环catch手工组合。
- **交付与模块**：新增有限parser chain，接受格式或callable，返回日期及选中规则并合并全部失败原因。；`src/dateutil/parser/__init__.py`、`src/dateutil/parser/_parser.py`。
- **兼容边界**：只捕获声明的解析异常，不吞编程错误/BaseException；不更改默认parse优先级。
- **正常验收**：已知格式先胜出，次选ISO按顺序执行，全部不匹配时报清楚各阶段原因。
- **异常／边界验收**：空chain、非字符串、kwargs传递、用户callable返回非法类型、fuzzy最终fallback和重复尝试。
- **原生回归**：`tests/test_parser.py`、`tests/test_isoparser.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；无。

## 20．普通解析器可选择接收秒级UTC偏移

- **类型／来源与场景**：enhancement；[来源](https://github.com/dateutil/dateutil/issues/1081)；历史本地记录带+05:21:10，应用需保留19270秒偏移。
- **原版现状／替代方式**：普通parse实跑ParserError；datetime.strptime(%z)和tzoffset秒值可替代。
- **交付与模块**：新增明确偏移秒扩展策略，解析HH:MM:SS并校验分量，复用现有tzoffset秒精度。；`src/dateutil/parser/_parser.py`、`src/dateutil/tz/tz.py`。
- **兼容边界**：不声称该形式是ISO8601必需；默认是否接受由兼容策略决定，不混入ISO日期严格承诺。
- **正常验收**：启用后+05:21:10得到utcoffset19270秒，字符串日期其他部分准确。
- **异常／边界验收**：负秒偏移、60秒分量、24小时边界、ignoretz、微秒偏移不支持时明确拒绝和格式歧义。
- **原生回归**：`tests/test_parser.py`、`tests/test_tz.py`。
- **实际依赖／步骤依赖**：沿用six和冻结tzdata；标准库日期/Decimal/时区接口，不新增服务或在线日历。；[3]。

未来每步包含实现、测试、文档及失败修复，在同一真实源码工作树累计。控制端冻结正反例、核对候选加载路径、观察实际日期/规则/本地文本结果，并回归原生和此前已接受能力。研究报告不等于独立冻结验收。
