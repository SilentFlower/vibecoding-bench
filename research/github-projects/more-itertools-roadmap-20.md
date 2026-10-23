# More-itertools：二十步真实工程路线

固定 [4aeb4338ae1407d8da9723e86da99efeb446f719](https://github.com/more-itertools/more-itertools/tree/4aeb4338ae1407d8da9723e86da99efeb446f719)。[原生审查](./more-itertools.md)记录完整测试、成本和取证。2 修复、18 增强（含性能），均尚未实施；新增名称是试点提案，默认既有语义保持。每步包含测试／文档，不拆重试或测试维度计数。

## 01．空集合的合法分区（修复）

- 来源：[上游 #1332](https://github.com/more-itertools/more-itertools/issues/1332)；more.py:set_partitions。实际原版空输入为 []。
- 交付：未指定 k 时返回唯一空分区 `[[]]`，让 Bell(0) 基础情形成立。
- 兼容：k=0 继续 ValueError，空输入显式 k=1 仍无分区；不改非空顺序。
- 验收：空列表／一次性迭代器等价；正常 n=1..5 计数一致；尺寸上限在无块时不制造虚假块。回归 tests/test_more.py:SetPartitionsTests；无前置依赖。

## 02．分区尺寸约束剪枝（性能增强）

- 来源：[上游 #1316](https://github.com/more-itertools/more-itertools/issues/1316)；set_partitions。原版9项 max_size=1 递归 helper 36,696次只产生一个结果。
- 交付：根据 n、最小／最大块尺寸跳过不可能的 k，结果及顺序与生成后过滤一致。
- 验收：小规模网格与独立枚举等价，显式不可能 k 迅速结束；profile 的无效分支显著减少，不以某台机器绝对毫秒为通过条件。
- 兼容／边界：无尺寸限制的行为保留；零／负尺寸和 min>max 按现有公开规则处理。tests/test_more.py:SetPartitionsTests；第01步只用于组合空集回归。

## 03．重入 partition 保持输入顺序（修复）

- 来源：[上游 #1315](https://github.com/more-itertools/more-itertools/issues/1315)；recipes.py:partition。谓词读取另一分支时，原版真分支得到 [2,1]。
- 交付：在支持的分支重入情形保持各分支原始相对顺序，不将仅优化吞吐的基准当作修复证明。
- 验收：[1,2] 重入场景为 [1,2]，混合真假和先消费任一分支均一致；递归进入同一活动生成器应清楚拒绝而非死锁。默认缓存与谓词异常传播保持；tests/test_recipes.py:PartitionTests，无前置依赖。

## 04．seekable 绝对位置与缓存窗口（增强）

- 来源：日志解析恢复场景；已读 more.py:seekable。当前 seek(0) 指缓存起点，缺少绝对 tell／缓存窗口元数据。
- 交付：新增 tell、seek_absolute 和可读缓存绝对范围；既有相对缓存 seek 语义不动。
- 验收：向前、回读、peek 和 bool 后位置准确；maxlen淘汰后越出历史窗口明确报错，maxlen=0仍不丢元素；空流／耗尽行为可判定。tests/test_more.py:SeekableTest，无前置依赖。

## 05．严格验证排序数据（增强）

- 来源：[上游 #1225](https://github.com/more-itertools/more-itertools/issues/1225)；more.py:is_sorted 只判断相邻顺序，不验证偏序／NaN的一致性。
- 交付：独立 validate_sorted 对有限数据做成对比较一致性与等价类验证，失败携带位置，默认 is_sorted 不变。
- 验收：正常整数／自定义全序通过；NaN、反对称／传递规则违反和未排序输入给确定错误；比较回调异常保留，max_items 限制拒绝无限收集。tests/test_more.py:IsSortedTests；明确 O(n²) 成本，无前置依赖。

## 06．无界惰性质数流（增强）

- 来源：[上游 #1168](https://github.com/more-itertools/more-itertools/issues/1168)；现有 sieve(n) 需要上界，nth_prime 是索引查询。
- 交付：primes() 分段地产生无限质数，可由 islice／takewhile 限制，不提前构造无限表。
- 验收：前十项、指定有限范围与独立试除金标准一致；段边界、从首项停止和较大有限前缀没有漏重，记录随已达范围增长的缓存成本。tests/test_recipes.py:PrimeFunctionTests；不声称缓存恒定，无前置依赖。

## 07．按时间间隙划分会话（增强）

- 来源：按事件间隙归并访问日志；现有 split_when 需自行编写时间规则。
- 交付：sessionize(iterable, key, gap) 保留完整事件，超过阈值才开始下一组。
- 验收：空流、等于阈值、跨日、连续单项会话和一次性流；倒序时间、负 gap、混合不兼容时间类型拒绝，不访问真实时钟。more.py 复用 split_when；tests/test_more.py:SplitWhenTests，默认函数不改。

## 08．事件时间滑动窗口（增强）

- 来源：按时间范围统计传感器流；windowed 的窗口大小是项数，不能表达最近30秒。
- 交付：windowed_time 按已排序事件时间和指定跨度维护窗口，定义开始／结束边界和输出时点。
- 验收：密集／稀疏、同时间戳、空流、恰在边界，缓存只保留有效窗口；倒序／非正跨度清楚报错。more.py:windowed 与 recipes.py:running_statistics 回归；不将处理时间混成事件时间，无前置依赖。

## 09．有序流归并关联（增强）

- 来源：两个已按业务键排序的CSV流关联；join_mappings要求现成映射，缺少通用顺序流关联入口。
- 交付：merge_join 提供 inner/left/full 模式，按键惰性合并；相同键多值生成有定义的笛卡尔组合。
- 验收：两边缺键、重复键、空输入、不同长度和单次生成器；乱序输入可选严格拒绝。more.py 新入口及 groupby_transform、spy 回归；缓存与最大重复键组相关，不虚报常量内存，无前置依赖。

## 10．时间点最近前值关联（增强）

- 来源：事件流关联生效时间不晚于事件的最近配置／报价；等值关联不能替代该规则。
- 交付：asof_join 按已排序时间选最后一个不晚于左项的右项，支持显式 tolerance 和无匹配哨兵。
- 验收：同时间、超过容忍差、右侧空、重复时间选最后项、跨区间；倒序／负容忍差拒绝。more.py 新入口回归 spy／peekable；保留前值而非缓存全表，不依赖第09步，二者业务语义不同。

## 11．公平笛卡尔积（增强）

- 来源：枚举多个可能无界的候选流；partial_product只保证每值出现，不枚举所有组合，product会先缓存输入。
- 交付：fair_product 用对角次序枚举，确保任一有限位置的组合终会出现。
- 验收：有限输入结果集合等于独立 product，两个 count 的有限前缀覆盖不同方向；空维、单维、有限与无界混合不饿死。more.py:partial_product、gray_product 回归；明确前缀缓存增长和可选预算错误，不承诺无限流常量内存。

## 12．有界有序并发映射（增强）

- 来源：逐条文件元数据计算需要并发但结果按输入排序；现有 serialize／callback_iter 不提供此映射协议。
- 交付：bounded_parallel_map 使用标准库线程池，限制在途项并维持结果顺序。
- 验收：屏障控制的乱序完成仍有序输出，消费提前结束／异常时停止继续提交；运行中的回调不能强制终止，资源关闭策略明确。more.py 新入口及 threading相关原生回归；无外部执行器服务，不把多线程测试称CPU加速保证。

## 13．按权重交错多个流（增强）

- 来源：两个数据源按2:1配额混流；interleave_randomly等概率，interleave_evenly按总长度分配。
- 交付：interleave_weighted 使用明确整数配额的确定次序，各源内部顺序不动，耗尽源退出调度。
- 验收：2:1的稳定前缀、提前耗尽、空源和无限源前缀；零／负／数量不符的权重拒绝。more.py:interleave_randomly/interleave_evenly回归；不复制完整输入，无前置依赖。

## 14．采样使用独立随机源（增强）

- 来源：两个实验在同进程互不干扰地复现 reservoir 采样；sample 当前仅使用模块级随机函数。
- 交付：sample 增加 rng 参数，覆盖普通／加权／counts 三个已有分支。
- 验收：同环境同源种子重复结果一致，两个源互不污染，未提供rng保持旧调用；错误RNG接口、k=0、权重／计数冲突仍确定拒绝。more.py:sample与tests/test_more.py:SampleTests；保留上游跨数学库构建不保证位级一致的说明。

## 15．严格解压列（增强）

- 来源：表格ETL需要发现畸形行；unzip当前按首行宽度，子列在缺项时停止，多余列不输出。
- 交付：unzip(strict=True) 对每个读取行核对宽度，在首次不符处抛带行位置错误；默认保留宽容模式。
- 验收：等宽单次流、短／长行、首行空、空表，不因各列消费速度不同漏掉错误；此前合法前缀允许已输出。more.py:unzip/iter_suppress、tests/test_more.py:UnzipTests，无前置依赖。

## 16．异常转换旁路回调（增强）

- 来源：数据清洗需收集坏行位置，map_except当前只能忽略指定异常。
- 交付：map_except／filter_except 可选 on_error 回调接收索引、原项和异常；成功结果流保持。
- 验收：两类被捕获错误各通知一次，未列异常继续传播，回调自身错误不吞；惰性消费只处理已请求前缀。more.py两个函数与原生对应Tests；错误记录由调用者持有，不无界缓存。

## 17．嵌套展开循环检测（增强）

- 来源：业务配置容器可能自引用；collapse目前按层数／类型遍历，不提供环检测。
- 交付：opt-in detect_cycles 按活动路径识别环，清楚报告；同一子列表在不同分支重复出现仍都输出。
- 验收：自循环、互循环、共享DAG、base_type和levels的停止边界；默认现有行为与字符串处理不变。more.py:collapse及TestCollapse，不将全局见过的ID误当成路径环。

## 18．分桶缓存预算（增强）

- 来源：只消费一个bucket时，其他键数据会无界缓存，当前文档也提示此成本。
- 交付：bucket 提供 max_cache_items、可读缓存统计及明确溢出错误；维持默认无限制。
- 验收：未被消费的键填满预算、排空后可继续、validator拒绝键不占缓存；允许并记录一个待分配前看项，不能丢掉它。more.py:bucket及BucketTests；预算是项目数，不声称限制任意对象的字节大小。

## 19．并发复制流的背压与退出（增强）

- 来源：concurrent_tee的慢消费者使共享链长期增长，目前没有可关闭分支和缓冲预算。
- 交付：显式 max_buffer 和 close 分支；慢分支超过预算时在继续读取上游前明确失败，可在落后分支推进后重试，不默丢数据。
- 验收：线程屏障下各分支顺序一致、关闭分支释放滞留、异常／耗尽不死锁；默认不关闭调用者拥有的上游。more.py:concurrent_tee及相应线程Tests；非阻塞溢出策略避免顺序消费死锁，不声称绝对线程取消。

## 20．带长度迭代器的可选真实性校验（增强）

- 来源：sized_iterator文档明确不验证长度，进度条和批处理需要知道声明长度是否真实。
- 交付：strict=True 在实际耗尽／发现额外项时报告长度不符，不提前物化输入；默认仅报告长度的行为保留。
- 验收：长度正好、过短／过长、0、非法长度、一次性迭代器和提前停止；过长检查可能读取首个多余项，须文档说明。more.py:sized_iterator及SizedIteratorTests，无前置依赖。

## 验收和计数

控制端冻结逐步正反例，实际加载候选包，检查输出顺序、消费次数、异常、缓存和关闭状态；按模块累计回归，修改共享模块后阶段性跑765主项及21,194子项。未来性能优化用等价结果和操作量验证，不靠某台机器的固定秒数。二十步在原工程累计修改；未声称已经实施或接入平台。
