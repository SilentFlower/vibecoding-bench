# Cachetools：二十步原生工程路线

固定 [tkem/cachetools@6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd](https://github.com/tkem/cachetools/tree/6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd)，版本 7.2.4。以下是一项已复现修复与十九项增强研究，尚未实现，不代表上游承诺。逐项原版观察在 `.deploy/github-100-research/core-utils/cachetools/observations-result.json`。

每步包含实现、文档、正常与边界验收，并运行原生 `python -m pytest tests` 累计回归；不把测试、锁的不同组合或失败重试拆步。已有七类缓存、定制 key/getsizeof/timer/ttu、锁、condition 防击穿、cache_info/cache_clear、expire 返回过期项均保留。以下新入口名称为提案。模块路径均相对 `src/cachetools/`，测试路径相对仓库根。

## 01．类访问 cachedmethod 接受合法关键字接收者（修复）

- 来源：[官方 #446](https://github.com/tkem/cachetools/issues/446)；已读 `_descriptor.py:_Unbound.__call__`。原版 `Example.get(self=obj,value=1)` 抛无实例异常，位置与绑定形式均返回 1。
- 交付：按被包装方法签名取得 receiver，支持其真实参数名；位置专用 receiver 仍必须位置传递。
- 验收：默认 self、其他名字、位置专用、缺失／重复 receiver、继承与 super、autospec；`tests/test_cachedmethod.py`／`test_classmethod.py`。保留无接收者调用报错，不简单 pop 固定名 self。

## 02．可序列化实例访问缓存方法后仍可往返（增强）

- 来源：[官方 #417](https://github.com/tkem/cachetools/issues/417)。原版访问前 pickle 52 字节成功，访问方法后因本地 Wrapper 类失败；上游未保证此能力，按增强处理。
- 交付：明确支持可 pickle 的业务状态和缓存内容；重建 wrapper，不把锁、condition、闭包内部等待集强行持久化。保留实例统计政策的文档约定。
- 验收：只访问／调用后、继承覆盖、多个方法、不同 pickle 协议、不可序列化业务数据仍清楚失败；`test_cachedmethod.py`。仅对可信的自生成数据往返，不以 pickle 处理外部快照。

## 03．按函数签名归一化缓存键（增强）

- 来源：配置计算的 f()、f(1)、f(x=1) 业务等价。实测三次均 miss；`keys.py` 四种 key 只处理实参，缺省参数不自动补齐。
- 交付：opt-in signature key 工厂，bind 实参并 apply_defaults，支持 typed 选择；原默认 hashkey 不变，已有自定义 key 替代方式继续可用。
- 验收：位置／关键字等价、默认 None、变长实参、关键字顺序、非法绑定、不可哈希值；`tests/test_keys.py`／`test_cached.py`，不把不同业务参数错误合并。

## 04．共享缓存的方法命名空间（增强）

- 来源：实例多个方法共享一个 mapping。默认 methodkey 不含方法名，原版 double(2) 后 triple(2) 同得 4；文档允许手工 partial 自定义前缀，不称现有契约 bug。
- 交付：显式 namespaced key 工厂，包含稳定业务命名空间与参数，可按实例／方法隔离；不采用进程地址作持久标识。
- 验收：同参数不同方法、同方法不同实例策略、继承覆盖、tuple 命名空间、非哈希命名空间；`test_keys.py`／`test_cachedmethod.py`。默认 methodkey 和主动共享键用法保留。

## 05．装饰器定向失效与在途结果隔离（增强）

- 来源：修改单条配置后只清除对应调用。已有 cache/cache_key 可手工删除，cache_clear 只能清全表，没有协调锁与在途计算的定向入口。
- 交付：cache_invalidate(*args,**kwargs) 复用真实 key 和锁；选定失效后旧计算不得重新写回，明确是否返回被删除状态。世代处理同时覆盖全量 clear。
- 验收：命中／缺失、方法缓存、并发等待、clear／单键失效发生在计算中、异常完成；`test_cached.py`／`test_cachedmethod.py`／`test_threading.py`。只阻止过期写回，不声称取消用户函数。

## 06．按计算结果决定是否缓存（增强）

- 来源：短暂返回 None 的外部配置读取。当前 cached 不提供结果谓词，用户可写自定义 mapping 过滤，但需重复处理装饰器语义。
- 交付：opt-in should_cache(key,value)；不缓存仍返回本次计算值，统计口径明确，条件等待者可继续重算。
- 验收：None／False／0 区分、拒绝后再次计算、谓词抛错、ValueError 过大值、锁与 condition 组合；`test_cached.py`／`test_cachedmethod.py`。默认缓存所有正常结果，不缓存函数异常的规则保留。

## 07．显式可控的失败负缓存（增强）

- 来源：不存在的本地索引键被密集重复查询；当前异常每次执行，不提供异常缓存政策，手工包装成功结果可替代。
- 交付：opt-in 选定 Exception 类型及独立有效期，记录可重建错误数据；避免长期保留 traceback 和业务对象，不缓存 BaseException、取消或进程中断。
- 验收：选中／未选中异常、到期重试、成功覆盖失败、异常带参数、同键等待唤醒；`test_cached.py`／`test_threading.py`。默认异常处理不变，不泛化成自动重试功能。

## 08．同键等待的截止期限（增强）

- 来源：condition 的 wait_for 没有装饰器层超时选项，某次慢计算会让其他请求无限等待；锁与 condition 防击穿本身已存在。
- 交付：可选等待超时及明确 TimeoutError；使用单调时间计算剩余期限，不取消正在执行的 leader。
- 验收：及时完成、等待超时、伪唤醒、异常唤醒、后续调用恢复、不同键并发；`test_threading.py`／`test_cachedmethod.py`，fake clock／事件同步避免仅凭 sleep 的脆弱断言。

## 09．同线程循环计算及时报告（增强）

- 来源：带 condition 的 memoized 递归函数重入同键。原版受控子进程 0.5 秒不返回，已杀死并回收；源码 pending 不区分 owner。
- 交付：opt-in 循环计算检测，记录 owner 与调用链，抛专用错误；不同线程等同键继续等待，不同键递归继续正常。
- 验收：直接同键／跨函数环、合法递归、函数异常后状态清理、两线程同键；`test_threading.py`。这是保护增强，不将所有递归阻塞称为原版违反承诺。

## 10．异步函数的原生缓存装饰器（增强）

- 来源：asyncio 读取流程；当前同步 wrapper 缓存函数返回对象，不提供 async_cached、asyncio 锁与取消政策，可另用 async-lru 等外部库。
- 交付：独立 async_cached／方法入口，缓存 await 完成的值，同键共享在途任务，明确调用者取消与共享计算的关系；不改变同步 cached。
- 验收：二次 await、并发同键、不同键、异常、一个等待者取消、事件循环关闭、显式清理；新增异步测试并回归 `test_cached.py`。异步兼容的 key／缓存操作仍须明确，不后台创建隐藏线程。

## 11．统一缓存移除原因事件（增强）

- 来源：需要区分容量淘汰、过期、显式删除与清空。可 subclass popitem/expire，但过期路径直接调用 Cache.__delitem__，没有统一事件入口。
- 交付：可选 observer，稳定传递 key/value/reason；说明回调执行时机、失败政策和禁止重入的操作。一次移除恰好一个事件。
- 验收：七类缓存、过期替换、clear、无效删除、回调抛错；`test_cache.py`／`test_lru.py`／`test_ttl.py`／`test_tlru.py`。默认无 observer 的成本与行为保留。

## 12．运行中调整容量（增强）

- 来源：进程内存配额动态收缩。maxsize 是只读属性，实测赋值 AttributeError；重新建缓存可替代，但会丢热数据。
- 交付：resize 保留策略元数据，缩小时按该缓存淘汰政策移除；支持清楚的非负容量校验，禁止 NaN 等无法比较的预算。
- 验收：增大不丢值、缩小淘汰、容量 0、加权值、过期值、七类缓存一致性；`tests/__init__.py` 公共测试契约及各策略测试。外部锁仍由调用者提供，不自称缓存实例突然线程安全。

## 13．不改变热度的查看（增强）

- 来源：监控预览不应将冷键变热。LRU/LFU 的 getitem 会改变策略，contains 不返回值；强调调用基类绕过会漏掉 TTL 校验，非通用替代。
- 交付：peek 提供值／default 而不更新次序、频率；时间缓存照常拒绝过期值，不触发 __missing__ 加载。
- 验收：查看后淘汰顺序不变、LFU 次数不变、过期／缺失／None 值、子类 missing；`test_lru.py`／`test_lfu.py`／`test_ttl.py`／`test_tlru.py`。

## 14．保持值不变的有效期续期（增强）

- 来源：会话活跃续期。重写相同值可以间接续期，但会经过大小计算与写入政策，没有专用 touch。
- 交付：TTL/TLRU 的显式 touch，保留当前值并重算截止时刻；明确是否改变 LRU 热度，过期键不复活。
- 验收：续期前后时刻、正好过期、缺失键、TLRU 自定义 ttu、计时器异常、重复续期不留幽灵堆项；`test_ttl.py`／`test_tlru.py`。默认读取不自动续期。

## 15．只读查询条目的剩余有效期（增强）

- 来源：本地状态页需展示重算时间。已有 ttl 是配置常量、timer 是计时器，未公开每条剩余时间和截止时刻。
- 交付：remaining_ttl／有效期元数据入口，不改变热度，不泄漏内部 link/item 对象；兼容自定义可减时间类型，不能假定只有浮点秒。
- 验收：TTL 与逐条 TLRU、缺失／到界／过期、datetime 计时器、查看不续期；`test_ttl.py`／`test_tlru.py`。与第 14 步读写目的不同，可独立交付。

## 16．显式重新计量可变缓存值（增强）

- 来源：缓存列表变长后内存会变化。原版 getsizeof 仅插入时调用，实测列表从 1 项变 2 项而 currsize 仍 1；这是文档约定下的增强。
- 交付：reweigh(key) 重新计算已存值成本并按容量淘汰；定义单值变得过大时保留／移除策略，不隐式监听任意对象修改。
- 验收：增大／缩小／零成本、变得超大、负成本／NaN、getsizeof 抛错、键自身被淘汰；`tests/__init__.py`／`test_lru.py`／`test_ttl.py`，不留下失真的 currsize。

## 17．限制单次过期清理工作量（增强）

- 来源：大量同刻过期项会让一次 expire 构建大列表并阻塞；原版三项均在一次调用中清除，签名只有 time。
- 交付：独立 budgeted expiration 入口或明确 limit 参数，最多移除 n 个有效条目；继续查询过期项时仍不可见，允许后续继续清理。
- 验收：limit 0／1、连续多次恰好清完、TLRU 已移除堆项、容量写入必须释放足够空间、事件一致；`test_ttl.py`／`test_tlru.py`。普通 expire 默认完整行为保留，不以 limit 假装物理内存已全部释放。

## 18．抵抗顺序扫描的分段 LRU 策略（增强）

- 来源：热点配置与一次性扫描共存；原版 LRU 实测短扫描后 hot 被淘汰，现有策略中没有 SLRU。
- 交付：独立 SLRUCache，probation/protected 两段、命中晋升、保护段溢出降级，明确容量比例与加权大小政策。
- 验收：热点保留、纯扫描不超限、晋升降级、更新／删除／clear、容量 0／1、getsizeof；新增策略测试并满足 `tests/__init__.py` 共有契约。非承诺所有负载都优于 LRU，比较明确可重复的命中轨迹。

## 19．跨进程可用的受控时间缓存快照（增强）

- 来源：离线任务重启希望恢复缓存。普通 pickle 可持久化部分实例，但默认 monotonic 截止时刻没有跨进程绝对含义；当前没有声明快照格式与重基时钟政策。
- 交付：显式 snapshot/restore，记录剩余寿命及格式版本，用户提供受限值编解码器；定义停机时间扣减／不扣减政策，不默认反序列化任意 pickle。
- 验收：换计时器基点、已过期项、非法格式版本、非有限剩余寿命、解码失败与预算截断；`test_ttl.py`／`test_tlru.py`。恢复验证后才发布，不污染已有缓存。

## 20．有界的过期值临时服务与后台刷新（增强）

- 来源：配置读取允许短时间旧值以避免刷新尖峰；TTLCache 到期即 miss，condition 会等待新值，不等价于 stale-while-revalidate。
- 交付：独立 opt-in 包装器，fresh/grace/dead 三阶段，grace 返回旧值并触发单次刷新；注入显式管理的 executor，说明刷新异常与关闭政策。
- 验收：fresh 命中、grace 同键只刷一次、dead 不再返回旧值、刷新失败、显式失效、executor 关闭、容量约束；新增刷新状态测试并回归 `test_threading.py`／`test_ttl.py`。不把第 10 步作为硬依赖，同步 executor 方案可独立交付。

## 独立验收边界

尚未实施这些能力；只通过原版适用测试与观察。冻结验收应加载候选的真实 cachetools 模块，用受控 timer、事件／线程、实际文件读取和缓存命中计数检查结果，累计此前接受的能力。平台仍需原生 API 适配和预算验证，研究路线不能当已上线功能。
