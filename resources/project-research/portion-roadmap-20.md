# Portion 二十步迭代研究路线

固定[AlexandreDecan/portion@622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44](https://github.com/AlexandreDecan/portion/tree/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已存在集合代数、replace/apply、AbstractDiscreteInterval、create_api、iterate自定义step/base/reverse、IntervalDict.get补空隙、find、binary combine(missing/pass_interval)、to_data/from_data可配置无穷标记；20步只扩展明确新行为，不重复计这些能力。

## 01．迭代器增加进度校验与明确有限消费控制

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/func.py)；日程点采样需要在step配置无效时明确报错，而不是重复输出同一点。
- **原版现状／替代**：iterate按调用者step推进，实跑step0前3项都是1；不承诺现有API自动校验方向，无limit。
- **交付与模块**：提供checked迭代选项，校验每次严格前进/后退，并支持max_items和明确起始base。；`portion/func.py`。
- **兼容边界**：默认兼容或清楚公布更严格参数校验；自定义step不可只凭数值正负判断；无界输入仍可惰性消费。
- **正常验收**：合法数值/日期步进一致，零步/停滞callable在有限调用内明确失败，limit确实限制消费。
- **异常／边界验收**：reverse方向错误、浮点精度停滞、空区间、不相交片段和无穷起点。
- **原生回归**：`tests/test_func.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 02．提供可直接使用的整数和日期离散区间

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；常见编号或自然日期集合不想每个应用自行继承抽象类型。
- **原版现状／替代**：已有AbstractDiscreteInterval和create_api，可自写_step/_incr/_decr；无导出的IntegerInterval/DateInterval。
- **交付与模块**：增加明确整数、date的一步离散实现及对应API模块，定义开放端点的规范化。；`portion/interval.py`、`portion/api.py`、`portion/func.py`。
- **兼容边界**：不替换默认连续Interval；datetime不自动按日期截断，bool/混合端点的接受策略明确。
- **正常验收**：整数(1,4)规范为[2,3]，日期按天相邻自动合并。
- **异常／边界验收**：date极值增减、空区间、无界、子类保持与序列化往返。
- **原生回归**：`tests/test_discrete.py`、`tests/test_func.py`、`tests/test_io.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 03．提供可注入度量的区间总量接口

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；统计可用会议时长或离散编号数量，len不能解释为长度。
- **原版现状／替代**：len返回原子片段数，busy两个片段len2；无measure/cardinality，可自行累加端点差。
- **交付与模块**：新增measure(metric)与受限离散计数协议，定义空集、单点和无界结果。；`portion/interval.py`、`portion/func.py`。
- **兼容边界**：保留len的片段数语义；任意可比较端点不必可相减，因此无默认通用长度。
- **正常验收**：[9,11)|[13,14)时长3；整数离散[1,3]计数3。
- **异常／边界验收**：空集、单点连续测度0、无穷、Decimal/timedelta返回类型和不支持度量错误。
- **原生回归**：`tests/test_interval.py`、`tests/test_discrete.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 04．按切点返回不自动重并的区间分区

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；在10点和12点把时间窗拆成三段供分别处理。
- **原版现状／替代**：Interval构造会把相接片段归并，不能用其本身保存有意切开的分区；无split。
- **交付与模块**：新增split(points,ownership=...)返回有序原子区间序列，明确切点归属。；`portion/interval.py`、`portion/func.py`。
- **兼容边界**：返回分区序列，不破坏Interval自动最简表示；原对象不变。
- **正常验收**：[9,13)按10/12切成[9,10)/[10,12)/[12,13)，并集等于原集且不重叠。
- **异常／边界验收**：区间外切点、重复切点、已开端点、非原子输入和singleton。
- **原生回归**：`tests/test_interval.py`、`tests/test_func.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 05．按固定跨度切成连续时间块

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/func.py)；把可用窗口切为30分钟预约段，末尾不足可保留或丢弃。
- **原版现状／替代**：iterate生成点，缺少生成子区间的chunks，可调用方手写相邻点拼接。
- **交付与模块**：新增chunks(span,alignment,remainder)并保持原始开闭边界与片段间空隙。；`portion/func.py`、`portion/interval.py`。
- **兼容边界**：与点迭代区分；不跨原集合空隙生成预约；日期跨度和实际秒数策略由端点算术声明。
- **正常验收**：[9,12)按1切三段，零碎尾段按策略处理。
- **异常／边界验收**：零/负跨度、起点对齐、无界必须limit、单点、reverse和浮点误差。
- **原生回归**：`tests/test_func.py`、`tests/test_interval.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 06．增加周期域的跨零区间适配

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；每日营业22点到次日2点应表示一个周期内的两段。
- **原版现状／替代**：默认全序区间closedopen(22,2)为空；无cyclic类型，可手工[22,24)|[0,2)。
- **交付与模块**：新增CyclicInterval适配器，显式period/origin并规范化跨零及多周期跨度。；`portion/interval.py`、`portion/func.py`、`portion/api.py`。
- **兼容边界**：不改变普通反向端点为空的契约；闭合整周期与空区间须有明确区分。
- **正常验收**：24小时周期22到2覆盖23和1、不含12，集合运算归一到同一周期。
- **异常／边界验收**：跨度0/整周期、多圈、负端点、不同period不可直接运算和端点开闭。
- **原生回归**：`tests/test_interval.py`、`tests/test_func.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 07．区间提供保留开闭端点的仿射变换

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；数轴窗口从摄氏转华氏或平移预约时刻。
- **原版现状／替代**：可apply逐片段手写，没有translate/affine；replace只调整整体enclosure并非通用逐点变换。
- **交付与模块**：新增affine(scale,offset)与translate，对负scale交换端点及开闭边界。；`portion/interval.py`、`portion/func.py`。
- **兼容边界**：不重用__sub__改变集合差；scale0变singleton，不能用原闭开组合误删全部。
- **正常验收**：[1,3)乘-2加1得到(-5,-1]，多片段平移保持空隙。
- **异常／边界验收**：scale0、无穷、Decimal、不可算术端点和不同离散类型的返回规则。
- **原生回归**：`tests/test_interval.py`、`tests/test_func.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 08．提供命名明确的Minkowski区间算术

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；把活动可开始时间集合与持续时间集合求可能结束时间。
- **原版现状／替代**：只有集合并交差，无Minkowski入口；__sub__当前是集合差。
- **交付与模块**：新增minkowski_sum/difference，按片段组合求端点并规范化结果。；`portion/interval.py`、`portion/func.py`。
- **兼容边界**：不改变现有运算符；离散与连续域的可达值语义分别声明。
- **正常验收**：[1,2]+(3,4]得到(4,6]，多片段与参考组合一致。
- **异常／边界验收**：空集、singleton、无界未定式、端点精确性、离散步幅和组合规模预算。
- **原生回归**：`tests/test_interval.py`、`tests/test_func.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 09．提供到区间的距离与最近点信息

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；预约编辑器需要提示离可用窗口还有多久，开放端点可能只有下确界。
- **原版现状／替代**：只有contains/overlaps，缺distance/nearest；可手工遍历。
- **交付与模块**：新增metric距离及NearestResult区分已达到的最近点与仅有infimum。；`portion/interval.py`。
- **兼容边界**：不为任意端点臆造距离；开放区间外点不能谎称最近点就是不包含的边界。
- **正常验收**：点8到[9,11)距离1且最近点9；点12到[9,11)距离1但无达到点。
- **异常／边界验收**：内部点距离0、空集、两个等距片段、离散邻点、无界和自定义metric。
- **原生回归**：`tests/test_interval.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 10．可按显式容差合并小空隙

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；传感器可用段间极小间隙可按业务容差视为连续。
- **原版现状／替代**：标准union只合并真实相接/重叠；_mergeable不收tolerance。
- **交付与模块**：新增coalesce(max_gap,metric)，返回近似后的区间并可报告被填补空隙。；`portion/interval.py`。
- **兼容边界**：默认集合代数精确不变；明确此操作增加集合元素，不把approximation伪装等价。
- **正常验收**：[1,2]|[2.1,3]容差0.2合成[1,3]并报告(2,2.1)。
- **异常／边界验收**：容差0、负值、浮点边界、开端点单点空隙、自定义日期差和无穷。
- **原生回归**：`tests/test_interval.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 11．提供原子区间的Allen关系分类

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；日程规则希望区分相接、部分重叠、包含及同起点。
- **原版现状／替代**：已有adjacent/overlaps和部分排序关系，无完整relation入口；不能把相邻等同全部Allen分类。
- **交付与模块**：新增AllenRelation枚举与relation(other)，先限制非空原子区间并定义开闭边界扩展。；`portion/interval.py`。
- **兼容边界**：非原子输入要求分片关系报告或明确拒绝；不改变现有<与adjacent语义。
- **正常验收**：标准13类样例互斥完整，交换两参数得到对应逆关系。
- **异常／边界验收**：相同端点不同开闭、singleton、空集、无穷和不同端点类型。
- **原生回归**：`tests/test_interval.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 12．IntervalDict提供统一值转换和筛选

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/dict.py)；本地时间价格表想把全部价格含税转换或删掉暂停条目。
- **原版现状／替代**：有find按值定位、binary combine，无map_values/filter_values。
- **交付与模块**：新增返回副本的transform_values，回调可带当前区间并使用专门DROP哨兵删除。；`portion/dict.py`。
- **兼容边界**：None可为合法值，不能当删除标记；变换后相等值按原规则归并。
- **正常验收**：价格乘1.1覆盖原domain，DROP部分仅删对应区间，原表不变。
- **异常／边界验收**：回调异常、相等值合并、非原子key、所有值删除和不hashable数据。
- **原生回归**：`tests/test_dict.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 13．多时间表一次覆盖聚合并保留来源

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/dict.py)；合并三份日程获得每个时间段全部活动和占用数量。
- **原版现状／替代**：combine只接一个other，调用方可重复两两combine但来源缺失和边界分裂管理复杂。
- **交付与模块**：新增overlay_many扫线分区，回调接收各输入的present/value及interval，支持来源/计数聚合。；`portion/dict.py`、`portion/interval.py`。
- **兼容边界**：保留binary combine；区分缺失和显式None；聚合结果以同值归并的语义明确。
- **正常验收**：三个重叠窗口输出每段正确来源集合和覆盖次数。
- **异常／边界验收**：空输入、同一端点不同开闭、singleton、无界、相等值与回调异常。
- **原生回归**：`tests/test_dict.py`、`tests/test_interval.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 14．为IntervalDict点和范围查询建立原子段索引

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/dict.py)；大量不同值时，高端点查询不应总从表头扫描。
- **原版现状／替代**：__getitem__从_storage头逐值区间扫描，顶部查询走更多前缀；不是本轮已测性能结论。
- **交付与模块**：维护原子段有序索引，以二分定位候选并同步写入/删除/合并；保留按值归并主表示。；`portion/dict.py`。
- **兼容边界**：非原子key按同值归并，不能仅按整体lower二分后漏掉后段；写入成本和额外内存公开。
- **正常验收**：相同数据所有点/区间查询等价参考实现，靠近上界不遍历全部无关前缀。
- **异常／边界验收**：一个值有多片段、开闭相邻、singleton、删除产生空隙、批量写入一致性。
- **原生回归**：`tests/test_dict.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 15．值归并可显式选择业务相等策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/dict.py)；两条展示数据对象按ID归并，而不依赖完整对象==。
- **原版现状／替代**：构造只有mapping_or_iterable，__setitem__/update用==/!=判断归并。
- **交付与模块**：新增value_equal或value_key策略，并在find/combine/copy/变换中统一保留。；`portion/dict.py`。
- **兼容边界**：默认==保持；不要求值可hash；非等价或非确定比较结果明确拒绝或声明责任。
- **正常验收**：同ID不同展示字段按声明策略合并，默认仍保留原比较行为。
- **异常／边界验收**：比较器异常、None、不可hash值、copy继承策略和不同策略表合并。
- **原生回归**：`tests/test_dict.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 16．区间表批量编辑可整体提交或撤销

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/dict.py)；一次导入多条新价目表，某条端点错误时不能留下半份更新。
- **原版现状／替代**：update逐run写入，无transaction；可应用自己copy后替换引用。
- **交付与模块**：提供atomic_update或编辑事务，以暂存存储完成排序/比较后统一commit。；`portion/dict.py`。
- **兼容边界**：普通update原覆盖顺序保持；明确事务期间旧views的可见性，无数据库/并发隔离承诺。
- **正常验收**：合法多行一次生效，后段失败时原表与domain完全不变。
- **异常／边界验收**：输入生成器异常、值比较异常、重复重叠覆盖、主动rollback和嵌套事务。
- **原生回归**：`tests/test_dict.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 17．提供不可变的IntervalDict快照

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/dict.py)；本地缓存或撤销栈需要保存不会随后续编辑改变的时间表。
- **原版现状／替代**：Interval可hash但IntervalDict可变无FrozenIntervalDict；copy为浅copy仍可写。
- **交付与模块**：新增FrozenIntervalDict保留点/范围查询与combine，修改入口拒绝并支持hash或明确不可hash值策略。；`portion/dict.py`。
- **兼容边界**：只冻结映射结构，不声称深冻结任意value对象；与mutable副本互转。
- **正常验收**：冻结后原mutable再改不影响快照，快照自身写入失败。
- **异常／边界验收**：不hashable值、共享可变value说明、反序列化、空表和copy类型保持。
- **原生回归**：`tests/test_dict.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 18．区间表提供带端点类型的可移植数据编码

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/io.py)；把含date/Decimal/无穷边界的日程保存到标准JSON后完整恢复。
- **原版现状／替代**：to_data/from_data只处理Interval，默认用非标准JSON Infinity，可自传标记；无IntervalDict编码。
- **交付与模块**：新增带版本的interval/dict codec，端点和value由显式注册codec处理，无穷用标签结构。；`portion/io.py`、`portion/dict.py`。
- **兼容边界**：保留旧to_data形状和conv；不执行编码内的类型名表达式，不自动导入用户模块。
- **正常验收**：date与Decimal表json.dumps(allow_nan=False)成功，加载后值/边界/类型等价。
- **异常／边界验收**：未知schema/codec、标记与普通字符串碰撞、空/非原子key、None、精度与许可归属。
- **原生回归**：`tests/test_io.py`、`tests/test_dict.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 19．引号边界文本提供明确语法和错误位置

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/io.py)；字符串端点自身含逗号或括号，仍希望可靠读写区间。
- **原版现状／替代**：from_string可配置bound/sep正则和conv，但默认分隔不理解引号，错误只报整串无法解析。
- **交付与模块**：新增可选quoted语法解析器与ParseError位置，支持escape、单点/区间/并集并向conv交付解码文本。；`portion/io.py`。
- **兼容边界**：保留正则自定义入口；不把既有可配置regex称完全无法支持此类数据。
- **正常验收**：包含逗号和括号的字符串端点导出再导入正确，错误能定位具体token。
- **异常／边界验收**：未闭引号、转义反斜杠、空文本、Unicode、literal inf与真正无穷的区别。
- **原生回归**：`tests/test_io.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

## 20．建立端点和值的泛型类型契约

- **类型／来源与场景**：enhancement；[来源](https://github.com/AlexandreDecan/portion/blob/622e7ca1f3a36a7cb337e6f51abeef0ee5e40c44/portion/interval.py)；静态检查项目需要区分date区间、numeric区间及映射值类型。
- **原版现状／替代**：核心API无泛型参数/注解，contains无类型信息；open接口支持多种可比较端点。
- **交付与模块**：增加Interval[T]与IntervalDict[T,V]类型声明、重载和py.typed，说明compare/step/measure协议。；`portion/interval.py`、`portion/dict.py`、`portion/func.py`、`portion/io.py`、`pyproject.toml`。
- **兼容边界**：不缩窄运行时已有可比较类型；保留Python3.10+兼容，不强制引入typing_extensions运行依赖。
- **正常验收**：date端点推断保持，点查询返回V、区间查询返回IntervalDict[T,V]。
- **异常／边界验收**：inf哨兵联合类型、conv返回类型、离散子类、混合错误端点及空区间工厂。
- **原生回归**：`tests/test_interval.py`、`tests/test_dict.py`、`tests/test_func.py`、`tests/test_io.py`。
- **实际依赖／步骤依赖**：运行依赖sortedcontainers~=2.4；测试pytest/pytest-cov/pytest-benchmark，默认benchmark skip按上游配置保留；无需外部服务。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
