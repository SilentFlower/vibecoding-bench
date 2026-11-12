# Agate：二十步真实工程迭代路线

固定 [wireservice/agate@202796ada63357c275a2a5f8685a983e37bad9bf](https://github.com/wireservice/agate/tree/202796ada63357c275a2a5f8685a983e37bad9bf)，详见[单仓审查](./agate.md)。共 20 步：19 项增强提案、1 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．连接键用实际列索引解析（问题修复）

- 来源／场景：https://github.com/wireservice/agate/issues/827
- 原版现状：复合right_key=[0,1]经列名tuple.index失败；相同值的两右列用.index(Column)删错列。两表现当前提交均复现。
- 交付目标：统一使用已解析Column.index，保留正确右键列排除与输出字段。
- 影响模块：agate/table/join.py；agate/columns.py
- 兼容边界：本步合并两个同根列解析症状；原名称、索引、复合与callable键语义保持。
- 正常验收：复合索引键匹配正确，identical copy/key列只去除指定key，保留copy。
- 异常／边界：名称/索引混用、重复值列、投影columns、full_outer及无匹配回归。
- 原生回归：tests/test_table/test_join.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．时间间隔中位数和分位数（增强提案）

- 来源／场景：https://github.com/wireservice/agate/issues/761
- 原版现状：Sum/Mean已支持TimeDelta，Median/Percentiles只允许Number；已用1秒/3秒对照复现拒绝。
- 交付目标：将Median与同一分位数体系支持TimeDelta，结果类型和插值单位明确。
- 影响模块：agate/aggregations/median.py；percentiles.py；agate/utils.py
- 兼容边界：不重复计已存在的Mean；默认Number统计保持，返回timedelta而非Decimal秒数。
- 正常验收：1秒/3秒中位数为2秒，奇偶样本和分组结果正确。
- 异常／边界：空列、None、负时长、微秒精度及极值溢出按明确策略。
- 原生回归：tests/test_aggregations.py；tests/test_table/test_aggregate.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．显式权重的统计聚合（增强提案）

- 来源／场景：agate/aggregations/mean.py 与现有聚合集合；固定源码：[agate/aggregations/mean.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/aggregations/mean.py)。
- 原版现状：均值/方差/分位数等是无权重聚合，没有WeightedMean等原生类；应用可用Formula和Sum组合。
- 交付目标：新增weighted聚合族，首先交付加权均值、总体方差与明确加权分位数规则。
- 影响模块：agate/aggregations 新类；Number数据类型
- 兼容边界：权重来源必须明确同长度数值列，不重定义已有Mean/Variance。
- 正常验收：销量加权单价结果符合手算，零权重不贡献，TableSet.aggregate保持类型。
- 异常／边界：负权重拒绝、总权重为0、成对NULL、极大Decimal和非数值列。
- 原生回归：tests/test_aggregations.py；tests/test_tableset/test_aggregate.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．按顺序计算滚动窗口指标（增强提案）

- 来源／场景：agate/computations/base.py；agate/table/compute.py；固定源码：[agate/computations/base.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/computations/base.py)、[agate/table/compute.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/compute.py)。
- 原版现状：Computation支持整表生成列，但无RollingMean/窗口框架。
- 交付目标：新增Rolling计算，显式窗口长度、min_periods和可选partition键，保持输入顺序。
- 影响模块：agate/computations；agate/table/compute.py
- 兼容边界：不隐式排序，调用方先order_by；默认Table不可变，原数据不改。
- 正常验收：订单按日期计算最近3行移动平均，不同分组不串窗口。
- 异常／边界：窗口<=0、NULL规则、短分组、重复排序值和空表类型正确。
- 原生回归：tests/test_computations.py；tests/test_table/test_compute.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．前后记录值的 Lag/Lead 计算（增强提案）

- 来源／场景：[agate/computations/change.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/computations/change.py)
- 原版现状：Change比较同一行两列，不提供跨行位移；没有Lag/Lead类。
- 交付目标：新增Lag/Lead，指定位移和分组，返回原列类型与明确边界默认值。
- 影响模块：agate/computations 新类；Table.compute
- 兼容边界：不是把现有Change改成相邻行差；顺序由调用方固定，不自动重排。
- 正常验收：按客户对比前笔消费，位移1/2和Lead保持原行数与类型。
- 异常／边界：分组边界、None、超长位移、空表、非法默认值和原表不可变。
- 原生回归：tests/test_computations.py；tests/test_table/test_compute.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．相对日期解析的固定参考时刻（增强提案）

- 来源／场景：[agate/data_types/date_time.py:DateTime.__init__](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/data_types/date_time.py)
- 原版现状：_source_time在构造时取当前日午夜，但不能公开注入参考时刻；同一输入跨日可能不同。
- 交付目标：Date/DateTime允许reference_datetime，固定相对表达式解析起点。
- 影响模块：agate/data_types/date.py；date_time.py
- 兼容边界：未指定时保留当前行为；格式化和ISO解析不被参考时间改变。
- 正常验收：固定参考下“tomorrow/next Monday”等重复运行得到同一日期，pickle后保持。
- 异常／边界：时区、夏令时、无日期文本、非法参考类型与显式datetime_format优先级。
- 原生回归：tests/test_data_types.py；tests/test_type_tester.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．类型推断的来源与排除理由（增强提案）

- 来源／场景：[agate/type_tester.py:TypeTester.run](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/type_tester.py)
- 原版现状：只返回最终类型，假设集合和被哪些样本排除不可查询。
- 交付目标：提供inspect_types，逐列返回样本范围、候选类型、最终选择与有限失败位置。
- 影响模块：agate/type_tester.py；agate/table/__init__.py
- 兼容边界：普通run返回不变；默认诊断不包含敏感原始值，只位置/异常类型。
- 正常验收：有日期/数字/文本混合列时可解释Number为何被排除，force字段可见。
- 异常／边界：limit=0/1、空列、全NULL、未知force名、短行和诊断上限。
- 原生回归：tests/test_type_tester.py；tests/test_data_types.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．显式schema与数据约束校验（增强提案）

- 来源／场景：agate/table/__init__.py；agate/type_tester.py；固定源码：[agate/table/__init__.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/__init__.py)、[agate/type_tester.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/type_tester.py)。
- 原版现状：可指定DataType，但缺少统一nullable/唯一性/枚举/范围的表级契约验证结果。
- 交付目标：新增Schema.validate(Table)，输出结构化违反项，可选strict抛错，保持数据本身不变。
- 影响模块：独立agate schema模块；data_types与Table
- 兼容边界：不把CSV导入替换为ORM；已有cast异常保持，约束验证为显式后续能力。
- 正常验收：订单金额范围、订单号唯一、币种枚举与必填项统一检查。
- 异常／边界：全NULL、复合唯一键、错误约束类型、最大错误数与空表。
- 原生回归：tests/test_data_types.py；tests/test_table/test_from_csv.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．关联结果标记匹配来源（增强提案）

- 来源／场景：[agate/table/join.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/join.py)
- 原版现状：join可left/inner/full_outer，但没有indicator列区分left_only/right_only/both。
- 交付目标：增加indicator列与自定义列名，直观发现数据匹配差异。
- 影响模块：agate/table/join.py
- 兼容边界：默认不加列，保留所有连接类型与原字段类型。
- 正常验收：全外连接三类订单分别标记，重复匹配一对多仍标both。
- 异常／边界：标记列名冲突、无匹配、NULL键、投影和行名称保留。
- 原生回归：tests/test_table/test_join.py
- 真实依赖：01

## 10．按时间的最近记录关联（增强提案）

- 来源／场景：agate/table/join.py；agate/table/order_by.py；固定源码：[agate/table/join.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/join.py)、[agate/table/order_by.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/order_by.py)。
- 原版现状：仅相等键/位置/callable连接，不能直接找某时间之前最近汇率。
- 交付目标：新增asof_join，明确时间键、方向、容差、分组和重复时间优先级。
- 影响模块：agate/table 新asof_join模块；DateTime/Number
- 兼容边界：不修改等值join；输入排序要求必须验证，不能默默全量排序改变次序。
- 正常验收：每笔交易附上同币种最近过去汇率，tolerance外为None。
- 异常／边界：无记录、相同时间多条、时区不兼容、正反方向和空表。
- 原生回归：tests/test_table/test_join.py；tests/test_data_types.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．关联空键是否相等的显式开关（增强提案）

- 来源／场景：[agate/table/join.py:right_hash](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/join.py)
- 原版现状：None可作为dict键，当前两个空键互相匹配；没有SQL式NULL不相等选项。
- 交付目标：join增加nulls_equal，False时任何含NULL的键不参与匹配。
- 影响模块：agate/table/join.py
- 兼容边界：默认True保持；复合键任一成员为None时按同一规则，不改变非空callable键。
- 正常验收：NULL订单号在False时只作为未匹配行，True时仍可匹配。
- 异常／边界：复合键、full_outer、require_match、重复NULL与indicator组合一致。
- 原生回归：tests/test_table/test_join.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．半连接与反连接（增强提案）

- 来源／场景：agate/table/join.py；agate/table/where.py；固定源码：[agate/table/join.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/join.py)、[agate/table/where.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/where.py)。
- 原版现状：当前需自行构造key集合或join后投影去重，没有semi/anti入口。
- 交付目标：新增semi_join/anti_join，只筛左行并保留左表schema和原行次序。
- 影响模块：agate/table 连接辅助模块
- 兼容边界：右表重复键不能重复左行；复用公开连接键解析，原left join不变。
- 正常验收：筛选有/无发货记录订单，左表每行最多一次且带原row_names。
- 异常／边界：NULL策略、复合/callable键、空右表、不匹配类型与大重复右表。
- 原生回归：tests/test_table/test_join.py
- 真实依赖：01

## 13．每个排序键单独指定方向和空值位置（增强提案）

- 来源／场景：[agate/table/order_by.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/order_by.py)
- 原版现状：key可多列，但reverse只有全局bool；NULL顺序随reverse整体翻转。
- 交付目标：允许明确SortKey(name,ascending,nulls)规格，稳定排序并保留row_names。
- 影响模块：agate/table/order_by.py；agate/utils.py:NullOrder
- 兼容边界：原key/reverse调用保持；不依赖给字符串加负号猜列名。
- 正常验收：地区升序、金额降序、NULL最后，重复键按原顺序稳定。
- 异常／边界：混合类型拒绝、缺列、空规格、callable现有行为、全NULL和空表。
- 原生回归：tests/test_table/test_order_py.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．可复现的随机／分层抽样（增强提案）

- 来源／场景：agate/table/__init__.py 的公共方法；where/limit；固定源码：[agate/table/__init__.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/__init__.py)。
- 原版现状：没有sample；可自行random选择行，但缺少保持schema/row_names的原生入口。
- 交付目标：新增sample(n或fraction,seed,strata)，明确无放回抽样与分层配额规则。
- 影响模块：agate/table 新sample方法
- 兼容边界：使用局部Random，不改全局随机状态；Table仍不可变，不承诺密码学随机。
- 正常验收：同种子样本相同，分层样本按约定配额，列类型和行名保持。
- 异常／边界：n大于行数、空组、非法比例、0行、配额余数与不同种子对照。
- 原生回归：tests/test_table；tests/test_mapped_sequence.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．CSV 分批构造不可变表（增强提案）

- 来源／场景：agate/table/from_csv.py；Table.__init__；固定源码：[agate/table/from_csv.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/from_csv.py)、[agate/type_tester.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/type_tester.py)。
- 原版现状：from_csv最终整表物化；row_limit只截取首批，不返回可继续读取的批次。
- 交付目标：增加iter_csv_tables，冻结一次明确schema后逐批生成原生Table。
- 影响模块：agate/table/from_csv.py；agate/type_tester.py
- 兼容边界：不把普通Table改成惰性对象；首批推断范围和后续不兼容值政策必须明确。
- 正常验收：万行合成CSV分批得到完整不重复行，批次类型一致并可独立聚合。
- 异常／边界：多行CSV、短末批、空输入、晚出现坏值、提前关闭和调用方文件所有权。
- 原生回归：tests/test_table/test_from_csv.py；tests/test_type_tester.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．成对数值列相关性（增强提案）

- 来源／场景：agate/aggregations 的现有单列统计集合；固定源码：[agate/aggregations/base.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/aggregations/base.py)、[agate/data_types/number.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/data_types/number.py)。
- 原版现状：现有均值/方差等主要单列，缺少Correlation/Covariance的两列组合聚合。
- 交付目标：新增成对样本的协方差与Pearson相关性，明确NULL配对删除规则。
- 影响模块：agate/aggregations 新类；Number
- 兼容边界：保持Decimal计算策略，不偷偷安装numpy；不把相关性当因果解释。
- 正常验收：线性正/负相关与已知手算协方差正确，TableSet也可分组计算。
- 异常／边界：常量列、0/1对样本、错类型、极大数和缺值位置不一致有确定结果。
- 原生回归：tests/test_aggregations.py；tests/test_tableset/test_aggregate.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．时区转换的列计算（增强提案）

- 来源／场景：agate/data_types/date_time.py；agate/computations/formula.py；固定源码：[agate/data_types/date_time.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/data_types/date_time.py)、[agate/computations/formula.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/computations/formula.py)。
- 原版现状：DateTime可带timezone参与解析，已有datetime对象直接返回；业务列转换要自写Formula。
- 交付目标：新增TimezoneConvert计算，明确源时区假设、目标时区与ambiguous/nonexistent规则。
- 影响模块：agate/computations 新类；DateTime
- 兼容边界：不把naive datetime默认为服务器本地；需显式源时区，原DateTime.cast保持。
- 正常验收：UTC交易时间转指定zone后代表同一instant，DateTime列类型和ISO输出一致。
- 异常／边界：夏令时重叠/缺失、无tz对象、无效zone、None和混合aware/naive拒绝或指定策略。
- 原生回归：tests/test_computations.py；tests/test_data_types.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．JSON 导出显式金额保真模式（增强提案）

- 来源／场景：[agate/data_types/number.py:Number.jsonify；table/to_json.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/data_types/number.py)
- 原版现状：Number内部Decimal但jsonify直接float；金额末位与大整数可能失真，现有默认如此。
- 交付目标：to_json增加number_mode=float/string/strict，string精确保留Decimal文本，strict拒绝无法精确保真的数。
- 影响模块：agate/data_types/number.py；agate/table/to_json.py
- 兼容边界：默认float兼容；不伪称标准json库原生支持任意精度Decimal数字文本。
- 正常验收：大整数、0.1与高精度金额在string模式往返不丢位，newline/keyed同样有效。
- 异常／边界：NaN/Infinity、None、负0、indent与newline互斥、第三方JSONEncoder优先级。
- 原生回归：tests/test_table/test_to_json.py；tests/test_data_types.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．按业务键比较两张类型表（增强提案）

- 来源／场景：agate/table/join.py；columns/rows类型结构；固定源码：[agate/table/join.py](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/join.py)。
- 原版现状：可通过join和where手工比对，没有返回added/removed/changed行的原生比较。
- 交付目标：新增Table.compare，以显式唯一键产出类型化变更表与列级差异。
- 影响模块：agate/table 新compare模块；join键解析
- 兼容边界：不做任意对象深比较；同表业务键须唯一，原表不改，NULL/Decimal/DateTime按数据类型比较。
- 正常验收：昨日/今日订单给出新增、删除和金额变化，变化列可定位。
- 异常／边界：重复键、schema新增/删除、类型不兼容、空表和选定忽略列政策。
- 原生回归：tests/test_table/test_join.py；tests/test_data_types.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．表和字段来源元数据随变换传递（增强提案）

- 来源／场景：[agate/table/__init__.py:Table._fork；rename/select/compute](https://github.com/wireservice/agate/blob/202796ada63357c275a2a5f8685a983e37bad9bf/agate/table/__init__.py)
- 原版现状：Table仅保存值、列名/类型、行名，没有明确来源/字段血缘元数据。
- 交付目标：增加可选不可变metadata与column_metadata，select/rename/join/compute按规则传播来源。
- 影响模块：agate/table/__init__.py；各_fork调用方
- 兼容边界：默认不附加额外输出，metadata不参与数据相等；不自动记录文件内容或凭据。
- 正常验收：CSV来源标签经select/rename保持，join标记左右列来源，compute标识派生。
- 异常／边界：同名来源合并冲突、嵌套可变值隔离、pickle/JSON可选导出和敏感字段显式排除。
- 原生回归：tests/test_table/test_rename.py；test_join.py；test_compute.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
