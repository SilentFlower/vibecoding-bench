# Pendulum 二十步迭代研究路线

固定[python-pendulum/pendulum@e06dacedc4cdea90fa1286b3965d180ab94cf251](https://github.com/python-pendulum/pendulum/tree/e06dacedc4cdea90fa1286b3965d180ab94cf251)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已支持区分日历add(days)与实际add(hours)、Interval.range锚点月末恢复、ISO duration解析、ZoneInfo/Timezone.from_file及文件pickle、time-machine旅行、泛型注解；未将这些现成能力重复计入。

## 01．Interval与timedelta相等时满足哈希契约

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/interval.py)；把同样一天的Interval和timedelta用作本地缓存键时不能得到两个相等键。
- **原版现状／替代**：实跑Interval==timedelta True，但hash不同且set长度2；Interval按端点hash，跨类型比较按duration。
- **交付与模块**：统一跨类型相等与hash设计，明确Interval身份/时长语义，选择兼容迁移路径。；`src/pendulum/interval.py`、`src/pendulum/duration.py`。
- **兼容边界**：若保留timedelta相等则hash必须用同一时长；不能只改字典测试或禁止合法键。
- **正常验收**：对所有a==b验证hash相等，相同端点Interval和对应Duration/timedelta表现一致。
- **异常／边界验收**：不同端点同长度、absolute标志、负区间、timezone/fold、反向比较与已有pickle。
- **原生回归**：`tests/interval/test_hashing.py`、`tests/interval/test_behavior.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 02．大时长和远距日期保留微秒整数精度

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/duration.py)；历史档案时间跨度很大，仍要保留原始1微秒尾数。
- **原版现状／替代**：Duration(days1000000,microseconds1)底层timedelta存1，但公开microseconds与as_timedelta实跑为0；归一化经过float total_seconds。
- **交付与模块**：在Duration分解、Interval构造和timedelta互转以整数天/秒/微秒运算，float仅用于明确浮点API。；`src/pendulum/duration.py`、`src/pendulum/interval.py`、`src/pendulum/datetime.py`。
- **兼容边界**：total_seconds仍可按标准float返回；精确字段和整数构造不应额外丢精度，年/月近似计量不改。
- **正常验收**：大时长微秒1可读出并往返，远距Interval精确等于标准库整数delta。
- **异常／边界验收**：负微秒、舍入进位、timedelta上下界、乘除round-half-even和日历分量。
- **原生回归**：`tests/duration/test_construct.py`、`tests/duration/test_arithmetic.py`、`tests/interval/test_construct.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 03．DateTime减Duration保留日历日语义

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/datetime.py)；夏令时开始日中午减一个日历日，应该仍是前日中午。
- **原版现状／替代**：纽约2026-03-08 12点减Duration(days1)实跑前日11点，subtract(days1)为12点；加法用_signature，减法却用_total秒。
- **交付与模块**：减法复用Duration完整日历/固定分量声明，与相应subtract关键字保持一致。；`src/pendulum/datetime.py`、`src/pendulum/duration.py`。
- **兼容边界**：普通timedelta仍代表实际经过时间；不把24小时和1日历日强制等同。
- **正常验收**：上述两入口得到相同前日12点；weeks/days/years/months混合也一致。
- **异常／边界验收**：DST回拨、负Duration、包含小时、月末截断、Interval作为timedelta子类的策略。
- **原生回归**：`tests/datetime/test_add.py`、`tests/datetime/test_sub.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 04．倒序Interval的成员判断与迭代一致

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/interval.py)；从周三到周一的倒序日期窗口也应包含周二。
- **原版现状／替代**：range(days)返回3日/2日/1日，但2日 in interval实跑False；contains只判断start<=item<=end。
- **交付与模块**：成员判断使用有向区间的无向覆盖边界，保留start/end与invert方向。；`src/pendulum/interval.py`。
- **兼容边界**：只改成员覆盖，range方向、Duration符号和absolute语义保持。
- **正常验收**：正序与倒序同两个端点的成员集合相同，端点包含策略一致。
- **异常／边界验收**：同端点、date/datetime混用、naive/aware、fold和范围外值。
- **原生回归**：`tests/interval/test_behavior.py`、`tests/interval/test_range.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 05．Duration的pickle与浅拷贝保留日历分量

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/duration.py)；保存一年两个月三天的业务时长后，恢复时仍能按日历加到日期。
- **原版现状／替代**：pickle和copy.copy后years/months都变0，remaining_days1；原为1/2/3，继承timedelta重建丢_signature。
- **交付与模块**：实现显式reduce/getstate重建全部Duration分量，保留AbsoluteDuration子类及历史协议兼容。；`src/pendulum/duration.py`。
- **兼容边界**：不只保留近似总秒；旧pickle可读取的兼容性明确，不自动改变年份365/月30的既有total。
- **正常验收**：pickle各协议、浅/深拷贝后日历分量和加到锚点结果相同。
- **异常／边界验收**：负/混合分量、微秒、子类、默认零值和进程内往返。
- **原生回归**：`tests/duration/test_behavior.py`、`tests/duration/test_arithmetic.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 06．Interval.range支持明确边界和有限输出策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/interval.py)；分页生成日程点时需要半开结束边界及最多30项。
- **原版现状／替代**：现有range含两端且无bounds/limit，amount0实跑前三项同一时间；当前未声称自动校验。
- **交付与模块**：新增closed/inclusive/limit策略并验证amount进度，保留锚点加累计步数。；`src/pendulum/interval.py`。
- **兼容边界**：默认含两端保持；负向区间由invert决定，不把amount0变无界业务特性。
- **正常验收**：半开不含end、limit限制消费，月步依旧1月31/2月28/3月31。
- **异常／边界验收**：0/负amount、无效单位、倒序、同端点、datetime极值与DST。
- **原生回归**：`tests/interval/test_range.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 07．日期时间支持指定步长的取整

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/datetime.py)；预约选择器把10:07:30对齐到15分钟网格。
- **原版现状／替代**：有start_of/end_of整单位，没有round/floor到任意步长和锚点。
- **交付与模块**：新增round_to(unit,step,mode,origin)，明确wall-time或实际时间线策略。；`src/pendulum/datetime.py`、`src/pendulum/date.py`、`src/pendulum/time.py`。
- **兼容边界**：不替代start_of/end_of；月/年不能按固定秒数实现；round平局策略公开。
- **正常验收**：15分钟floor为10:00、ceil10:15，half-even/half-up按声明。
- **异常／边界验收**：跨日、负时间差、DST缺失/重复、step非法、naive/aware与不同origin。
- **原生回归**：`tests/datetime/test_start_end_of.py`、`tests/time/test_behavior.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 08．注入节假日和周末规则的业务日历

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/date.py)；本地交期计算跳过周末和明确离线假日。
- **原版现状／替代**：无BusinessCalendar，可应用循环add(days1)并查假日。
- **交付与模块**：新增不可变business calendar，支持add_business_days、count和下一工作时刻，假日由调用方给出。；`src/pendulum/date.py`、`src/pendulum/datetime.py`、`src/pendulum/helpers.py`。
- **兼容边界**：不在线下载假日或假设所有地区周末相同；普通add(days)不变。
- **正常验收**：星期五加1工作日为星期一，若周一声明假日则星期二。
- **异常／边界验收**：负方向、起点非工作日、全周休息拒绝、跨年及节假日重复。
- **原生回归**：`tests/date/test_add.py`、`tests/datetime/test_add.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 09．财政周期可按明确规则计算

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/date.py)；报告财年从4月开始，或采用声明的4-4-5周历。
- **原版现状／替代**：quarter/year固定公历，无FiscalCalendar；可以自行计算。
- **交付与模块**：增加FiscalCalendar策略，返回fiscal_year/period/start/end并支持受限4-4-5规则。；`src/pendulum/date.py`、`src/pendulum/datetime.py`、`src/pendulum/helpers.py`。
- **兼容边界**：默认公历quarter/year保持；53周年的归属规则必须配置，不默认猜业务。
- **正常验收**：4月1日进入新财年；声明4-4-5样例各周期天数正确。
- **异常／边界验收**：闰年、53周、周起始、边界日、负/超范围周期和不支持规则。
- **原生回归**：`tests/date/test_start_end_of.py`、`tests/datetime/test_start_end_of.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 10．默认语言周界和本地时区可作用域隔离

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/__init__.py)；两个本地异步任务使用不同语言/周起始，不应互改全局。
- **原版现状／替代**：set_locale和week_starts_at写pendulum全局；无统一context管理器。
- **交付与模块**：新增ContextVar配置作用域，支持嵌套恢复并由相关API优先读取。；`src/pendulum/__init__.py`、`src/pendulum/helpers.py`、`src/pendulum/tz/local_timezone.py`、`src/pendulum/date.py`、`src/pendulum/datetime.py`。
- **兼容边界**：旧全局设置为无作用域回退；跨线程传播规则明确，不伪称OS timezone也线程局部。
- **正常验收**：两个async任务locale/week规则独立，退出/异常后恢复父配置。
- **异常／边界验收**：嵌套、取消、线程、显式参数优先级和测试fixture重置。
- **原生回归**：`tests/test_thread_safety.py`、`tests/date/test_start_end_of.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 11．Interval可连续切分为子区间

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/interval.py)；按月份拆分账期，希望完整覆盖原始起终点且无缝隙。
- **原版现状／替代**：range只给点，split/chunks入口不存在；应用需拼相邻点并处理最后残段。
- **交付与模块**：新增split/chunks返回相邻跨度，明确bounds与余段策略，基于上一边界推进。；`src/pendulum/interval.py`、`src/pendulum/datetime.py`。
- **兼容边界**：不改变现有range从原锚点恢复月底的契约；分段覆盖与点生成分开定义。
- **正常验收**：1月31到5月1日按月分段，无空隙无重叠且正好覆盖。
- **异常／边界验收**：月末、闰年、DST、倒序、limit、极短尾段和同端点。
- **原生回归**：`tests/interval/test_range.py`、`tests/interval/test_behavior.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 12．解析结果可附带类型与来源信息

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/parser.py)；导入界面需要知道输入被解释成Date/Time/DateTime/Duration及哪些字段用了默认。
- **原版现状／替代**：parse返回多类型且有**options；无parse_info报告，from_format也丢弃匹配过程。
- **交付与模块**：新增ParseResult含最终值、识别分支、显式字段、默认字段、时区来源和错误位置。；`src/pendulum/parser.py`、`src/pendulum/formatting/formatter.py`、`src/pendulum/__init__.py`。
- **兼容边界**：现有parse返回类型保持；不宣称默认日期/时区来自原文本；支持Rust/Python等价报告。
- **正常验收**：同一日期/时刻/时长各报告正确类型，缺时区明确标为default。
- **异常／边界验收**：含小数秒、ISO interval、歧义输入、多格式失败、Unicode索引与错误cause。
- **原生回归**：`tests/test_parsing.py`、`tests/parsing/test_parsing.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 13．批量解析保留行号并聚合失败

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/parser.py)；离线CSV一列日期需要逐行结果和错误，而不是遇一条坏值退出。
- **原版现状／替代**：无parse_many，调用方只能循环try/except。
- **交付与模块**：新增惰性parse_many with stop/collect策略，返回输入索引、值/ParseError并可固定本批now/default。；`src/pendulum/parser.py`、`src/pendulum/__init__.py`。
- **兼容边界**：不自动猜列全局格式；不把普通None当成功日期；复用同一解析规则而非新解析器。
- **正常验收**：三行中两合法一错误，结果保留顺序与准确原索引。
- **异常／边界验收**：生成器、空值、批次默认now固定、早停、类型约束和不保存敏感原文的可选截断。
- **原生回归**：`tests/test_parsing.py`、`tests/parsing/test_parsing.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 14．重复日程支持星期筛选和例外日期

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/interval.py)；每月最后一个工作日09点的本地提醒需要稳定生成。
- **原版现状／替代**：Interval.range已按原锚点累计月步，能恢复3月31；无Recurrence/例外/weekday规则对象。
- **交付与模块**：新增明确Recurrence，锚点、weekday/nth、count/until、例外日期及DST策略独立声明。；`src/pendulum/interval.py`、`src/pendulum/date.py`、`src/pendulum/datetime.py`。
- **兼容边界**：不重新计现有range月底恢复；可利用现有dateutil依赖但需明确日历与时区适配。
- **正常验收**：指定月内最后星期五生成正确序列，例外日删除且保留本地9点。
- **异常／边界验收**：缺少目标日、fold/gap、count/until冲突、倒序和序列化规则。
- **原生回归**：`tests/interval/test_range.py`、`tests/date/test_day_of_week_modifiers.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 15．日历Duration可在锚点计算实际经过量

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/duration.py)；1个月到底多少秒取决于起点，不能总当30天用于排程判断。
- **原版现状／替代**：Duration.months保留分量，但total_days按既有30天近似；没有at(anchor)接口。
- **交付与模块**：新增resolve_at(anchor)返回终点和实际delta，并提供按锚点比较两个calendar duration。；`src/pendulum/duration.py`、`src/pendulum/datetime.py`、`src/pendulum/interval.py`。
- **兼容边界**：现有total_days近似保持；明确按日历应用与混合分量先后，不令无锚点比较自动猜日期。
- **正常验收**：1个月从1月1和2月1得到不同实际时长，端点等于anchor.add(months1)。
- **异常／边界验收**：月底截断、闰年、DST、负时长、naive锚点和纯秒Duration。
- **原生回归**：`tests/duration/test_total_methods.py`、`tests/datetime/test_add.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 16．Duration可序列化为保留日历分量的ISO文本

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/duration.py)；业务模型已经parse(P1Y2M3D)，需要输出可交换的相同类型文本。
- **原版现状／替代**：ISO时长解析已有；Duration没有to_iso8601_string，str是自然语言。
- **交付与模块**：增加显式ISO duration serializer，保留year/month与固定分量、符号和小数秒。；`src/pendulum/duration.py`、`src/pendulum/parser.py`。
- **兼容边界**：不把普通总秒格式伪装保留月份；混合符号无法单一ISO表示时明确规范化/拒绝。
- **正常验收**：正负支持范围parse(to_iso(d))恢复同一日历分量及锚点效果。
- **异常／边界验收**：零值、微秒、weeks与days混合、超过秒精度、混合正负与AbsoluteDuration。
- **原生回归**：`tests/parsing/test_parsing_duration.py`、`tests/duration/test_in_words.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 17．时刻范围支持明确跨午夜规则

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/time.py)；营业22:00到02:00应明确表示次日结束，而不是简单取绝对差。
- **原版现状／替代**：Time.diff存在但不携带日期跨日语义，无TimeSpan类型。
- **交付与模块**：新增TimeSpan/clock span以日偏移表示结束，支持contains和duration，在需时区时绑定日期。；`src/pendulum/time.py`、`src/pendulum/interval.py`。
- **兼容边界**：不改变Time.diff当前语义；无日期时只算墙上时刻，不能声称真实DST秒数。
- **正常验收**：22到次日02得到4小时且包含23与01、不包含12。
- **异常／边界验收**：同起终点空/整日策略、微秒、超过一日、夏令时绑定日期及naive/aware。
- **原生回归**：`tests/time/test_diff.py`、`tests/time/test_behavior.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 18．时区数据提供方可固定来源和版本

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/tz/timezone.py)；同一离线报告在不同机器上需要说明使用哪份IANA数据。
- **原版现状／替代**：Timezone继承ZoneInfo且已有from_file并保留文件pickle；timezone工厂无provider/版本描述。
- **交付与模块**：新增TimezoneProvider封装显式离线tzdata源、版本/校验信息和按源隔离缓存，提供可复现构造。；`src/pendulum/tz/timezone.py`、`src/pendulum/__init__.py`、`src/pendulum/tz/__init__.py`。
- **兼容边界**：不重复提案已实现from_file和pickle；默认系统/包回退保持；不在线更新数据。
- **正常验收**：两个固定源的相同zone独立构造并能回溯数据身份，报告保存版本。
- **异常／边界验收**：缺zone、数据不匹配、缓存更新、相同key不同bytes、pickle与旧source失效。
- **原生回归**：`tests/tz/test_timezone.py`、`tests/tz/test_timezones.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 19．自然语言时长支持紧凑风格和精度控制

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/duration.py)；卡片希望2h34m或最多两单位，而详细页显示完整日历分量。
- **原版现状／替代**：Duration.in_words只有locale/sep，diff_for_humans采用固定阈值与单主单位，没有统一options。
- **交付与模块**：新增HumanizeOptions覆盖style/max_units/min_unit/rounding，语言数据支持声明范围。；`src/pendulum/duration.py`、`src/pendulum/interval.py`、`src/pendulum/formatting/difference_formatter.py`、`src/pendulum/locales/locale.py`。
- **兼容边界**：默认文本和阈值保持；缺语言短单位时回退策略明确，不对成品文本replace。
- **正常验收**：相同时长长/短风格与max_units一致，精度截断/舍入按声明。
- **异常／边界验收**：0、负数、微秒、复数、缺翻译、calendar duration和方向后缀。
- **原生回归**：`tests/duration/test_in_words.py`、`tests/interval/test_in_words.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

## 20．当前时间可由应用级Clock提供

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-pendulum/pendulum/blob/e06dacedc4cdea90fa1286b3965d180ab94cf251/src/pendulum/__init__.py)；本地业务测试希望冻结某个组件的now，而不修改整个进程时间。
- **原版现状／替代**：有Traveller/time-machine全进程时间旅行，now没有Clock参数或provider。
- **交付与模块**：新增Clock协议、SystemClock/FixedClock及可选作用域provider，today/解析默认now统一使用。；`src/pendulum/__init__.py`、`src/pendulum/parser.py`、`src/pendulum/testing/traveller.py`。
- **兼容边界**：现有travel/freeze保持；不宣称Time-machine当前没有作用；Clock只影响明确接入的Pendulum入口。
- **正常验收**：两个组件固定时钟独立，today/tomorrow与parse缺字段默认使用相同clock。
- **异常／边界验收**：async任务隔离、线程传播、时区转换、clock异常、scope退出和显式now优先。
- **原生回归**：`tests/testing/test_time_travel.py`、`tests/test_parsing.py`。
- **实际依赖／步骤依赖**：运行python-dateutil与tzdata；Rust扩展由maturin/PyO3构建。本次测试pytest、time-machine(test extra)、pytest-benchmark，冻结全部版本，无外部服务。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
