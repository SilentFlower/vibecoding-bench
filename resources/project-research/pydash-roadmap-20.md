# Pydash：二十步真实工程迭代路线

固定 [dgilland/pydash@ef6a6427e488e29e827e0e0819f2630ad3ff4cdc](https://github.com/dgilland/pydash/tree/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc)，详见[单仓审查](./pydash.md)。共 20 步：18 项增强提案、2 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．单界随机数遵守零起点契约（问题修复）

- 来源／场景：https://github.com/dgilland/pydash/issues/353
- 原版现状：random(start,stop=1)分不清省略stop，random(5)实际randint(1,5)，负数/0/小数同样违背docstring；已确定性mock复现。
- 交付目标：区分省略边界和显式提供，单界从0到该值，保留双界和无参规则。
- 影响模块：src/pydash/utilities.py:random；类型overload与chaining导出
- 兼容边界：random()仍0..1，显式反序上下界仍交换，不能仅把stop默认改0破坏关键字调用。
- 正常验收：正/负/零/浮点单界调用底层精确边界正确，chain结果一致。
- 异常／边界：stop关键字、显式0、floating、reverse bounds和生成类型存根回归。
- 原生回归：tests/test_utilities.py；tests/test_chaining.py；tests/test_annotations.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．重试回调不被假值布尔语义忽略（问题修复）

- 来源／场景：https://github.com/dgilland/pydash/issues/352
- 原版现状：on_exception通过truthiness判断调用，合法falsey callable始终不执行；当前三次失败的回调列表为空。
- 交付目标：用None表示未提供，所有合法callable都按尝试次数调用并验证参数。
- 影响模块：src/pydash/utilities.py:retry；helpers.py:getargcount/callit
- 兼容边界：保留重试次数、休眠、最终异常与可变参数兼容，不额外重试回调抛出的异常。
- 正常验收：FalseCallback收到[1,2,3]，普通回调和无回调对照保持。
- 异常／边界：__len__=0 callable、无参数回调、非法falsey值、非重试异常和最后一次。
- 原生回归：tests/test_utilities.py 的 retry
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．按键或值稳定排序字典（增强提案）

- 来源／场景：https://github.com/dgilland/pydash/issues/234
- 原版现状：有集合sort_by和to_pairs，但没有sort_dict_by_keys/values的保序字典接口。
- 交付目标：新增两种排序便捷函数，返回新dict，支持key与reverse、值同序稳定。
- 影响模块：src/pydash/objects.py；__init__.py；chaining类型
- 兼容边界：默认不修改输入，不宣称新dict影响其他数据结构迭代规则。
- 正常验收：按客户名称键或金额值排序，返回键值对应且重复排序值保原序。
- 异常／边界：不可比较混合类型明确交给key，空dict、自定义Mapping、FalseKey与回调异常。
- 原生回归：tests/test_objects.py；tests/test_chaining.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．JSON Pointer 形式的原生路径（增强提案）

- 来源／场景：[src/pydash/utilities.py:to_path/to_path_tokens](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：现有点/括号路径和key序列，不提供RFC6901斜杠与~0/~1转义入口。
- 交付目标：新增get_pointer/set_pointer等明确模式，适配JSON树与根空路径。
- 影响模块：src/pydash/objects.py；utilities.py 路径转换
- 兼容边界：不把普通/a路径自动改解释；保留受限属性key防护，仅JSON dict/list不走任意getattr。
- 正常验收：指向含斜杠/波浪号的键和数组下标，读写结果与路径序列一致。
- 异常／边界：非法~转义、缺字段、0开头索引、负数与append符号只在写入语义允许。
- 原生回归：tests/test_objects.py；tests/test_utilities.py；新增pointer集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．多路径修改的原子补丁（增强提案）

- 来源／场景：[src/pydash/objects.py:set_/update/unset](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/objects.py)
- 原版现状：每次原地修改，多个操作中途失败会留下前面成功修改；没有批量patch接口。
- 交付目标：新增patch_paths，先在受控JSON副本上执行set/remove/test等操作，成功后返回结果或一次提交。
- 影响模块：src/pydash/objects.py；helpers.py 路径写入
- 兼容边界：不声称任意Python对象或并发共享引用事务；原set_仍原地语义。
- 正常验收：修改客户地址并更新订单标签，全部成功得到新对象，test失败原对象完整不变。
- 异常／边界：重叠路径、数组移位、非法操作、后期类型错误和受限key均无半更新。
- 原生回归：tests/test_objects.py；tests/test_chaining.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．沿路径复制的不可变更新（增强提案）

- 来源／场景：[src/pydash/objects.py:update_with/set_with](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/objects.py)
- 原版现状：set_/update/unset均原地；clone_deep后修改会复制整个图，没有路径级结构共享接口。
- 交付目标：新增assoc_in/update_in/dissoc_in，以仅复制修改路径的dict/list实现不可变更新。
- 影响模块：src/pydash/objects.py；utilities.py:PathToken
- 兼容边界：原API不改；共享未修改子树须明确调用方只读约定，首版不支持循环图或任意属性对象。
- 正常验收：更新深层qty，根和路径容器是新对象，未修改分支identity保留。
- 异常／边界：不存在路径、list边界、None、根替换、循环输入拒绝与原对象不改。
- 原生回归：tests/test_objects.py；tests/test_chaining.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．声明式深合并冲突策略（增强提案）

- 来源／场景：[src/pydash/objects.py:merge_with/_merge_with](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/objects.py)
- 原版现状：已有iteratee可自写策略，但没有统一list replace/concat/unique与None保留/覆盖的声明参数。
- 交付目标：新增merge_policy入口，按路径规则选择容器冲突与NULL策略。
- 影响模块：src/pydash/objects.py:合并辅助
- 兼容边界：保留merge的按下标列表合并和iteratee旧规则；新接口是显式便利层。
- 正常验收：配置默认值+环境覆盖按指定路径替换列表、其他路径合并，来源对象不被修改。
- 异常／边界：类型冲突、重复JSON项、None、循环对象策略、非法规则和规则优先级明确。
- 原生回归：tests/test_objects.py 的 merge/merge_with
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．带实际来源路径的通配读取（增强提案）

- 来源／场景：[src/pydash/objects.py:get；utilities.py:to_path_tokens](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/objects.py)
- 原版现状：get只定位一个明确路径，*是普通键，没有orders[*].sku多匹配接口。
- 交付目标：新增get_wildcard，受限单层通配生成(path,value)序列并支持匹配数上限。
- 影响模块：src/pydash/objects.py；utilities.py 路径表达
- 兼容边界：不引入完整查询语言，旧get的字面*键保持；通配必须新接口显式。
- 正常验收：提取订单每个sku及精确索引，遍历顺序确定，字面特殊键可转义。
- 异常／边界：缺失分支、空容器、最大深度/匹配数、循环图拒绝、不访问受限属性。
- 原生回归：tests/test_objects.py；tests/test_utilities.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．将路径token序列转换为可读字符串（增强提案）

- 来源／场景：[src/pydash/utilities.py:to_path/to_path_tokens](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：可解析路径，却没有将token规范序列化回不歧义文本的公开接口。
- 交付目标：新增path_to_string，以可逆转义表示点号、括号、空键、数字字符串和整数索引。
- 影响模块：src/pydash/utilities.py:PathToken；路径解析器
- 兼容边界：不偷偷改变旧字符串解析；不能表示的非字符串/整数hashable键明确拒绝或保留序列形式。
- 正常验收：混合路径序列序列化后to_path读回完全相等，JSON编辑器可显示可重用位置。
- 异常／边界：反斜杠、引号、Unicode、空根、负索引及连续特殊符号往返。
- 原生回归：tests/test_utilities.py；tests/test_objects.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．深路径写入的显式增长预算（增强提案）

- 来源／场景：[src/pydash/helpers.py:base_set；objects.py:update_with](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/helpers.py)
- 原版现状：list目标大索引会补大量None，没有调用级最大路径深度／列表增长控制。
- 交付目标：新增bounded_set/update选项，预检查目标路径与预计增长，在副作用前拒绝超限。
- 影响模块：src/pydash/helpers.py:base_set；objects.py 新受控入口
- 兼容边界：默认set_保持；限额按实际新增槽位，不把dict数字键误算数组扩容。
- 正常验收：预算内新增orders[3]正常，巨大索引被明确拒绝且输入原状保持。
- 异常／边界：负索引、bool、嵌套多次扩容、customizer产生容器及预算0定义明确。
- 原生回归：tests/test_objects.py；tests/test_utilities.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．按元素惰性执行的迭代链（增强提案）

- 来源／场景：src/pydash/chaining/chaining.py；collections.py:map_/filter_；固定源码：[src/pydash/chaining/chaining.py](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/chaining/chaining.py)、[src/pydash/collections.py](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/collections.py)。
- 原版现状：chain是延迟整体求值，map/filter仍产列表；README建议大数据另用fnc，不能误称已有chain是流式。
- 交付目标：增加独立iter_chain，首版map/filter/take/终结聚合有明确惰性规则。
- 影响模块：src/pydash/chaining 新迭代链；collections.py 可复用iteratee
- 兼容边界：普通chain保持；不在流式链里隐式支持必须全量排序的操作，必要时显式collect。
- 正常验收：无限整数源map/filter/take(3)只消费足够项，结果与有限原链一致。
- 异常／边界：提前关闭、一次性源、回调错误、空源和过量消费检测，不将测试拆步骤。
- 原生回归：tests/test_chaining.py；tests/test_collections.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．混合同步和协程函数的异步 flow（增强提案）

- 来源／场景：[src/pydash/functions.py:Flow/flow/flow_right](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/functions.py)
- 原版现状：现有Flow同步串接，不await协程结果，没有async_flow。
- 交付目标：新增async_flow，逐步await awaitable并支持同步函数，返回单个协程调用。
- 影响模块：src/pydash/functions.py；公开导出和类型
- 兼容边界：原flow不变；不在内部asyncio.run抢占调用方事件循环。
- 正常验收：同步提取→异步合成处理→同步汇总按顺序完成，参数转发准确。
- 异常／边界：取消、异常中止后续、空函数列表、异常位置与嵌套事件循环兼容。
- 原生回归：tests/test_functions.py；tests/test_annotations.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．协程原生异步重试（增强提案）

- 来源／场景：[src/pydash/utilities.py:retry](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：同步retry只捕获调用时异常，async函数异常发生在await后，time.sleep也会阻塞事件循环。
- 交付目标：新增async_retry，以await与asyncio.sleep实现同类退避并正确传播取消。
- 影响模块：src/pydash/utilities.py；新增异步辅助
- 兼容边界：原retry保留同步；现有scale/jitter/max_delay契约复用，不默认捕获取消或BaseException。
- 正常验收：两次合成异常后成功，其他协程在等待期间继续运行，回调可同步或异步。
- 异常／边界：取消时不再重试、最终异常、非法配置、无sleep最后一次及虚拟时钟边界。
- 原生回归：tests/test_utilities.py；新增async测试
- 真实依赖：02

## 14．根据返回值决定是否重试（增强提案）

- 来源／场景：[src/pydash/utilities.py:retry](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：现有仅exceptions驱动，返回暂不可用结果会立即成功返回。
- 交付目标：增加retry_if_result显式谓词与结果耗尽策略，异常重试和结果重试可组合。
- 影响模块：src/pydash/utilities.py:retry
- 兼容边界：默认无谓词保持；区分最后结果返回与抛RetryResultError，不凭bool(result)擅自重试0/None。
- 正常验收：返回pending/pending/ready三次后停止，attempt数和回调信息准确。
- 异常／边界：FalseKey谓词、谓词异常、最终结果、混合异常/结果和不匹配异常传播。
- 原生回归：tests/test_utilities.py 的 retry
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．重试的总时限与合作取消（增强提案）

- 来源／场景：[src/pydash/utilities.py:retry](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：已有单次delay上限与次数，但没有整个重试循环的monotonic deadline/cancel_check。
- 交付目标：增加max_elapsed/cancel_check，在下一次调用及睡眠前检查并限制剩余睡眠。
- 影响模块：src/pydash/utilities.py:retry
- 兼容边界：不声称能中断已执行的任意同步函数；默认attempts规则不改。
- 正常验收：受控时钟到期后不多发一次调用，总等待不超剩余预算。
- 异常／边界：deadline边界、调用本身超时、取消回调异常、0预算和最后原异常可追溯。
- 原生回归：tests/test_utilities.py 的 retry
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．有容量与过期策略的记忆化（增强提案）

- 来源／场景：[src/pydash/utilities.py:memoize](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：memoized.cache是无界dict，无TTL/容量政策；调用方可以自行替换cache但没有内建策略入口。
- 交付目标：memoize增加可选cache_factory或策略对象，交付LRU+TTL参考实现和可注入时钟。
- 影响模块：src/pydash/utilities.py:MemoizedFunc/memoize
- 兼容边界：默认dict与现有cache可访问保持；不隐式缓存异常，resolver规则不改。
- 正常验收：相同key命中、容量逐出、到期重算，cache.clear/手动赋值行为明确。
- 异常／边界：FalseKey resolver、不可哈希key、TTL边界、对象修改与线程安全声明。
- 原生回归：tests/test_utilities.py；tests/test_annotations.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．异步记忆化合并同键在途调用（增强提案）

- 来源／场景：[src/pydash/utilities.py:memoize](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/utilities.py)
- 原版现状：对协程函数会缓存coroutine对象，不能安全多次await；没有async_memoize。
- 交付目标：新增async_memoize，同一事件循环同key共享在途Task，完成后缓存结果。
- 影响模块：src/pydash/utilities.py；异步缓存辅助
- 兼容边界：不同loop不共享Task；普通memoize保持，不默认缓存失败或取消。
- 正常验收：并发三次同key只执行一次合成协程，不同key可并行，后续直接取结果。
- 异常／边界：单等待方取消是否影响共享任务的规则、全取消、异常重试与cache清理明确。
- 原生回归：新增async memoize测试；tests/test_utilities.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．防抖和节流的可控待执行生命周期（增强提案）

- 来源／场景：[src/pydash/functions.py:Debounce/Throttle](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/functions.py)
- 原版现状：现有Timer是内部状态，没有public cancel/flush/pending接口。
- 交付目标：为包装器提供cancel、flush和pending，确保受控停止或立即执行最后待处理参数。
- 影响模块：src/pydash/functions.py:Debounce/Throttle
- 兼容边界：默认调用语义不变；cancel不声称回滚已经开始的回调，flush只执行当前代次一次。
- 正常验收：多次输入后flush只回调最新值，cancel后计时器不再调用，pending状态准确。
- 异常／边界：重入回调、Timer已开始、重复取消/flush、max_wait和last_result一致。
- 原生回归：tests/test_functions.py 的 debounce/throttle
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．链式执行的结构化跟踪（增强提案）

- 来源／场景：[src/pydash/chaining/chaining.py:ChainWrapper.unwrap](https://github.com/dgilland/pydash/blob/ef6a6427e488e29e827e0e0819f2630ad3ff4cdc/src/pydash/chaining/chaining.py)
- 原版现状：tap可看某个中间值，但没有自动记录每步方法名/耗时/失败位置的链跟踪。
- 交付目标：增加trace(callback)，对一次value调用产生步骤事件，默认只元数据。
- 影响模块：src/pydash/chaining/chaining.py；all_funcs接口
- 兼容边界：不默认序列化中间数据；chain仍可plant/重复调用，trace不冻结旧value或重执行步骤。
- 正常验收：filter/map/sum各产生一次有序事件，失败明确第几步，最终值不变。
- 异常／边界：嵌套链、重复求值、回调错误、耗时用单调时钟和中间值显式opt-in。
- 原生回归：tests/test_chaining.py；tests/test_functions.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．显式受限并发的集合映射（增强提案）

- 来源／场景：https://github.com/dgilland/pydash/issues/205
- 原版现状：map_是同步，用户可外部Executor；没有并发上限/顺序/异常策略的parallel_map入口。
- 交付目标：新增parallel_map，显式max_workers与最大在途项，默认保输入顺序并可使用调用方executor。
- 影响模块：src/pydash/collections.py；公开导出与类型
- 兼容边界：原map_保持，默认不自发并行现有chain；不承诺加速CPU绑定或强杀线程。
- 正常验收：合成可控IO回调出现并发但不超上限，输出顺序按选项，生成器不被全量预投放。
- 异常／边界：回调失败取消未开始项、输入异常、超时、空源和executor所有权正确收口。
- 原生回归：tests/test_collections.py；tests/test_chaining.py；新增并发集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
