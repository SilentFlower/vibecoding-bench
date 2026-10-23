# Toolz：二十步原生工程路线

固定源码为 [pytoolz/toolz@451af60dec590a6010e2babdbf391ea8f815122f](https://github.com/pytoolz/toolz/tree/451af60dec590a6010e2babdbf391ea8f815122f)。这是逐仓研究提案，尚未实施或获得上游接受。原版观察见 `.deploy/github-100-research/core-utils/toolz/observations-result.json`；前三项已实际复现，其余是业务场景与已读 API 对照得到的增强缺口。

每步同时交付实现、文档和验收；统一保留既有函数、curried/tlz 导出、签名与序列消费约定，并运行原生 `python -m pytest toolz`。新增适配的签名、序列化与 currying 按实际影响追加 `test_curried.py`、`test_signatures.py`、`test_serialization.py` 回归；这些工作不另计步。后续入口名为提案，不冒称已经存在。各步独立，无强制前置依赖。

## 01．零长度 tail 在序列与迭代器上保持一致（修复）

- 来源：[官方问题 #626](https://github.com/pytoolz/toolz/issues/626)，已读 `itertoolz.py:tail`。原版 `tail(0,[1,2,3])` 返回全部，迭代器返回空。
- 交付：零长度返回对应空结果，明确负数的非法输入约定；保留正常切片输入的结果类型，避免为取得零项消费整条迭代器。
- 验收：列表、元组、字符串、一次性流、空输入、超过总长；计数迭代器确认零请求不读取。原生 `toolz/tests/test_itertoolz.py`，兼顾 `last` 与正数 `tail`。

## 02．分批时保留与内部占位字符串相同的数据（修复）

- 来源：业务文本列可含任意字符串；已读 `partition`／`partition_all`，当前以字符串 `no_pad` 的对象身份判尾。实际 `partition_all(2,iter([1,no_pad]))` 丢弃末值。
- 交付：内部缺失标记不可与正常字符串碰撞；padding 参数显式给出同值字符串时仍视为真实填充值，保留批次类型与惰性。
- 验收：占位文本在首／中／末、完整／残缺批、无长度流、空输入、自定义比较对象；不能通过数据相等比较引入数组歧义。回归 `test_itertoolz.py` 的所有 partition 集合。

## 03．isdistinct 接受无长度的可重复数据源（修复）

- 来源：可重复读取的惰性查询源；已读 `isdistinct`。有 `__iter__` 但无 `__len__` 的对象原版抛 TypeError，同样的数据转 iterator 可正常返回 True。
- 交付：对没有可用长度的 Iterable 走单次扫描，不重复读取；保留可用序列快速路径与发现重复后的短路。
- 验收：可重复无长度源、一次性流、空源、首部重复、不可哈希值及数据源自己的真实异常；原生 `test_itertoolz.py`，不吞掉用户逻辑错误。

## 04．不可变嵌套删除 dissoc_in（增强）

- 来源：[官方需求 #579](https://github.com/pytoolz/toolz/issues/579)；`dicttoolz.py` 只有顶层 dissoc 与嵌套 assoc_in/update_in，已核对没有 dissoc_in。
- 交付：按键路径复制受影响分支并删除叶子；明确缺失路径忽略／严格、空父映射保留／清理策略。原对象与未修改分支不深拷贝。
- 验收：多级删除、兄弟键保留、缺失中间层、非映射中间值、空路径、factory；`toolz/tests/test_dicttoolz.py`，不把原生 dissoc 改为递归删除。

## 05．update_in 可禁止创建不存在的路径（增强）

- 来源：[官方需求 #515](https://github.com/pytoolz/toolz/issues/515)。当前会自动创建 account.score 并调用更新函数，签名没有禁止 upsert 的选项。
- 交付：显式 opt-in 的仅更新模式；路径不存在时返回约定的未更改映射，并保证不调用有副作用的 func；默认 upsert 继续适用。
- 验收：存在但值为 None、缺失叶子／祖先、func 抛异常、空路径和 factory。回归 `test_dicttoolz.py` 中 assoc_in 复用路径，不能把 None 当不存在。

## 06．按请求顺序投影映射字段（增强）

- 来源：[官方需求 #392](https://github.com/pytoolz/toolz/issues/392) 的外部 API 大映射裁剪。已有 keyfilter/get 可以手工组合，缺少同时约定请求顺序和缺失策略的原生投影。
- 交付：select_keys 以可迭代键集投影，提供缺失报错／忽略／填充；保留 factory，明确重复请求折叠。
- 验收：源顺序不同、一次性键生成器、重复与缺失键、None 键、tuple 键、严格失败不修改原映射；`test_dicttoolz.py`，保持 get 的 tuple-key 既有语义。

## 07．列式映射的流式重分批（增强）

- 来源：[官方需求 #580](https://github.com/pytoolz/toolz/issues/580)。merge_with 已能聚合成列，但 partition_all 只处理单序列，缺少字段对齐的重分批。
- 交付：rebatch_dict 接收有限字段名与可迭代列值，同步产生等长列批；严格长度或显式 padding，避免静默错位。首版支持普通 Python 列，不承诺 numpy 零拷贝。
- 验收：3→2 重批、空列、不同列长、一次性列、非正批量和消费计数；内存随列数×批量增长。`test_dicttoolz.py`／`test_itertoolz.py`，merge_with 现有行为保留。

## 08．两组业务对象生成创建／更新／删除计划（增强）

- 来源：[官方需求 #567](https://github.com/pytoolz/toolz/issues/567)。join 可以组合记录，但不提供按业务键比较变更与重复键政策的完整协调结果。
- 交付：reconcile 生成纯数据变更计划，允许 key 与等价判定函数；不执行数据库写入。结果顺序确定，重复键显式报错或采用声明策略。
- 验收：相同／新增／移除／内容变更、不同数据库 ID 但相同业务键、重复键、不可哈希键、比较器异常；`test_itertoolz.py`，原输入不变，不能把重复键笛卡尔积当更新计划。

## 09．已排序分组的有界内存聚合（增强）

- 来源：按客户排序的离线流水。reduceby 保存所有键的累加器，partitionby 会实体化整个连续组；两者都不是只保留当前组累加器的惰性输出入口。
- 交付：reduceby_sorted 对相邻同键组逐组归约并输出，支持 init 工厂与可选顺序校验；不声称未排序输入可全局聚合。
- 验收：超大单组不实体化、首组可提前输出、空源、None 初值、重复非相邻键的明确约定、校验失败；`test_itertoolz.py`／`test_recipes.py`，现有 reduceby 语义保留。

## 10．按指定层级变换嵌套列表与元组（增强）

- 来源：[官方需求 #400](https://github.com/pytoolz/toolz/issues/400)，已有 map/mapcat 是平面迭代，缺少层级选择和容器保留约定。
- 交付：map_depth 首版支持有限 list/tuple 的指定非负深度，保持容器类型和非目标节点；不复制完整 Mathematica levelspec，也不把字符串逐字符递归。
- 验收：深度 0／1／超过树高、混合叶子、空分支、回调异常、环形输入拒绝；`test_itertoolz.py`，共享子树不应被误判为活动路径环。

## 11．映射键变换的碰撞策略（增强）

- 来源：API 字段大小写归一化。keymap 当前将 {'A':1,'a':2} 静默覆盖为 {'a':2}，签名无碰撞策略；这是增强，未宣称违反其现有文档。
- 交付：opt-in error／first／last／combine 政策并报告原键冲突；默认仍 last，factory 保留。
- 验收：多个原键落同键、combine 抛错、不可哈希新键、输入为空、插入顺序与原映射不变；`test_dicttoolz.py`，itemmap/merge 的覆盖语义不随之改变。

## 12．有路径冲突解析的递归配置合并（增强）

- 来源：多层默认配置。merge 会整体替换子映射，merge_with 的回调只收到同层值，需要用户自行递归和维护路径。
- 交付：merge_recursive 提供路径感知 resolver；只对映射递归，列表／标量冲突由显式策略处理，输入保持不变。
- 验收：嵌套兄弟字段同时保留、映射与标量冲突、空源、factory、活动路径环、resolver 异常；`test_dicttoolz.py`。默认浅 merge 不变，不隐式拼接列表。

## 13．映射作为关键字上下文的管道（增强）

- 来源：[官方需求 #510](https://github.com/pytoolz/toolz/issues/510)。pipe 按单个位置参数传递 data；lambda/apply 能手写适配，但没有声明映射上下文及失败阶段的入口。
- 交付：独立 pipe_keywords 或明确适配器链，每阶段以关键字调用并要求返回映射；错误含阶段上下文并保留原异常链。不得改变 pipe 的位置参数语义。
- 验收：多阶段添加／删除字段、空链、缺必需字段、非字符串键、阶段返回非映射、回调自己抛 TypeError；`test_functoolz.py`，不以捕获 TypeError 自动猜调用方式。

## 14．按序列化成本预算分批（增强）

- 来源：数据库批写／消息体有字节上限。partition/partition_all 仅按项数，无法把不同尺寸记录按预算装批。
- 交付：partition_cost 接受 cost 函数、总预算和可选项数上限，保持输入顺序；单项超预算选择独立输出或报错，语义明确。
- 验收：正好到界、零成本、负成本／NaN、异常 cost、超大单项、无限输入的有限前缀；`test_itertoolz.py`，最多保留一个待分配项，说明该次预读。

## 15．单遍固定数量的蓄水池采样（增强）

- 来源：未知总长日志需要恰好 k 个样本。已有 random_sample 是逐项 Bernoulli 采样，结果数量不固定；random.sample 需要序列，均不等价。
- 交付：reservoir_sample 对有限流单遍、O(k) 空间采样，支持与 random_sample 一致的随机源注入；定义输入短于 k 的返回政策。
- 验收：种子重现、k=0 不读取、空源、短源、重复值按位置抽样、非法 k；`test_itertoolz.py`，确定性 stub 验证替换分支，不依赖偶然概率断言。

## 16．按键输出每条事件后的累计状态（增强）

- 来源：事件流实时账户余额。reduceby 只给最终字典，accumulate 只有一个累计状态；现有组合需自行维护逐键状态与输出快照。
- 交付：scanby 逐条惰性输出 key 与该组更新状态，init 工厂互不共享；可选状态数量预算，达到预算显式停止而非静默丢组。
- 验收：交错组、可变初值隔离、回调抛错、不足预算、超预算、有限前缀不消费后续；`test_itertoolz.py`，不能将先前输出引用在之后偷偷修改。

## 17．join 可声明关联基数约束（增强）

- 来源：维表错误重复会放大金额；原版重复左／右键产生完整笛卡尔积，join 签名没有 validate 参数，此为增强而非既有 bug。
- 交付：opt-in one-to-one／many-to-one／one-to-many 校验，失败说明侧与键；保留默认 many-to-many 及四种内外关联。
- 验收：两侧各两条重复、未匹配重复、None 作为普通键、生成器与回调异常；`test_itertoolz.py`。右侧校验是流式晚失败，明确可能已有前缀输出，不能声称事务式全有或全无。

## 18．merge_sorted 可校验输入流的排序前提（增强）

- 来源：分区文件意外未排序会产出错误合并；当前 merge_sorted([2,1],[3]) 原样产生 2,1,3，不检查先决条件。
- 交付：opt-in validate_sorted 按各源相邻值检测，错误带源编号与位置；用已有 key 时复用比较语义。
- 验收：重复键、多个空源、单源也校验、迟发逆序、key 异常、不可比较键；`test_itertoolz.py`。默认惰性与低内存保留，允许在发现前输出已消费前缀。

## 19．原生 memoize 的可限额缓存与观察接口（增强）

- 来源：长时间运行的纯函数 ETL。memoize 默认字典不设上限；已支持传入自定义 mapping，用户可接 cachetools 或用 functools.lru_cache，不能声称完全无法限额。
- 交付：在原生 currying 工作流中提供可选内置容量政策、clear/info 入口；无新第三方依赖，外部 cache 与内置预算互斥并明确报错。
- 验收：LRU 淘汰后重算、容量 0、命中统计、异常不缓存、用户 key、kwargs、clear、外部映射不被替换；`test_functoolz.py`／`test_curried.py`。不附带线程安全保证。

## 20．降序输入的惰性归并（增强）

- 来源：最新日志在前的多个分区。merge_sorted 仅实现升序；reverse=True 被 kwargs 接收但没有应用，实测 5,1 与 4,2 输出 4,2,5,1。
- 交付：明确支持 reverse 的降序归并；保持 key、同键稳定顺序、单源与空源快捷路径。旧版未文档化的 reverse 不称为已支持后失效的 bug。
- 验收：输出 5,4,2,1、升／降序的重复键稳定性、字典 key、一次性与无限流有限前缀；`test_itertoolz.py`。若启用第 18 步校验，校验方向必须一致；两步可独立交付。

## 后续验收边界

实际只运行原版基线和观察，未将上述预期输出称为已经通过。独立冻结验收应断言候选包的实际加载路径、可见数据结果与惰性消费；保留原生测试，逐步累计新增行为。无需统一 app.py；适用原生工程入口应另行接入平台。
