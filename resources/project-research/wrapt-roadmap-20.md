# Wrapt 二十步迭代研究路线

固定[GrahamDumpleton/wrapt@6b4e844950213118b19e613248d2bc9469eb731e](https://github.com/GrahamDumpleton/wrapt/tree/6b4e844950213118b19e613248d2bc9469eb731e)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已支持with_signature/with_doc、adapter factory、自动descriptor/async dunder、LazyObjectProxy同步首次初始化、async synchronized、mark_as_sync/async、sync/async桥、实例LRU缓存、wrapper_chain/find/unwrap/单目标scope和类型stubs；不重复列作新增。

## 01．类方法缓存保持实际调用类绑定

- **类型／来源与场景**：bug_fix；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；基类和派生类共享类方法定义，但返回值依赖cls。
- **原版现状／替代**：Base.label先调用后Derived.label实跑仍返回Base；单一parent缓存捕获首次bound __wrapped__。
- **交付与模块**：把调用类纳入绑定缓存身份或参数，确保继承方法不会固定到第一个访问类。；`src/wrapt/caching.py`。
- **兼容边界**：静态/普通函数共享缓存保持；类方法同参数但不同cls不应复用错误结果。
- **正常验收**：先Base后Derived和反向调用都各自返回实际类，缓存命中不重复计算。
- **异常／边界验收**：两种classmethod装饰次序、多个子类、覆盖/super、cache_clear范围和对象GC。
- **原生回归**：`tests/core/test_lru_cache.py`、`tests/core/test_inheritance.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 02．方法缓存可支持无字典的slots对象

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；轻量数据对象使用__slots__仍希望按实例缓存计算。
- **原版现状／替代**：当前缓存存实例属性，Slotted.compute实跑AttributeError；可让类额外留__dict__。
- **交付与模块**：新增显式cache storage策略，支持弱引用外置存储或用户指定cache slot，并定义生命周期。；`src/wrapt/caching.py`、`src/wrapt/weakrefs.py`。
- **兼容边界**：默认实例属性方式保持；外置cache不能因bound method强引用而阻止实例释放。
- **正常验收**：无__dict__但可weakref对象可缓存且GC后条目释放。
- **异常／边界验收**：不可weakref对象、不可hash实例、继承slot、并发首次调用和缓存回调持有self。
- **原生回归**：`tests/core/test_lru_cache.py`、`tests/core/test_weak_function_proxy.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 03．异步函数缓存已完成结果而非协程对象

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；本地async计算同参数第二次await应得到结果。
- **原版现状／替代**：普通lru_cache遵循functools方式缓存原返回协程，实跑第二次await RuntimeError；无async_lru_cache。
- **交付与模块**：提供独立async_lru_cache，只在成功await后缓存值，明确定义异常/取消与正在计算状态。；`src/wrapt/caching.py`、`src/wrapt/synchronization.py`。
- **兼容边界**：不改变同步lru_cache默认语义；不将复用协程对象称为支持结果缓存。
- **正常验收**：重复await同参数均得到4，真正计算次数按命中规则减少。
- **异常／边界验收**：不同事件循环、取消、异常是否缓存、实例隔离和并发未完成请求的明确策略。
- **原生回归**：`tests/core/test_lru_cache.py`、`tests/core/test_synchronized_markers.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 04．缓存支持按单调时间失效

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；本地配置派生结果只在30秒内复用。
- **原版现状／替代**：现有lru_cache只转发functools参数，没有TTL；可自写wrapper。
- **交付与模块**：新增ttl_cache或缓存策略，以可注入monotonic clock检查过期并结合容量淘汰。；`src/wrapt/caching.py`。
- **兼容边界**：默认LRU不变；过期从计算完成或开始计时必须声明；测试不用真实sleep。
- **正常验收**：假时钟推进前命中，越界后重算，过期条目不会无限保留。
- **异常／边界验收**：TTL0/负、时钟异常、长计算、slots存储和并发更新。
- **原生回归**：`tests/core/test_lru_cache.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 05．缓存键可按函数绑定参数规范化

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；f(1)、f(x=1)和显式默认参数按业务应共享同一缓存项。
- **原版现状／替代**：当前沿functools按调用形态构键，没有自定义key或canonical binding参数。
- **交付与模块**：新增显式key_func/bind_arguments策略，保留typed规则和参数默认值处理。；`src/wrapt/caching.py`、`src/wrapt/signature.py`。
- **兼容边界**：默认functools键行为保持；不默认深hash任意可变输入。
- **正常验收**：三种等价调用在canonical模式只计算一次，自定义提取record_id可用于dict输入。
- **异常／边界验收**：positional-only、keyword-only、varargs、默认可变对象、key函数异常和键碰撞责任。
- **原生回归**：`tests/core/test_lru_cache.py`、`tests/core/test_with_signature.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 06．缓存可只失效指定一次调用

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；某个商品数据改动后只清除对应参数的计算结果。
- **原版现状／替代**：已有cache_clear全清，没有cache_invalidate；functools内部键不公开。
- **交付与模块**：提供invalidate(*args,**kwargs)及删除返回状态，使用与读取完全相同键策略。；`src/wrapt/caching.py`。
- **兼容边界**：不通过清空全部冒充选择性失效；命中统计重置规则明确。
- **正常验收**：只清除id1，id2下一次仍命中，实例之间互不影响。
- **异常／边界验收**：不存在项、canonical默认参数、正在计算、过期条目和线程竞态。
- **原生回归**：`tests/core/test_lru_cache.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 07．同键并发计算可合并为一次执行

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/caching.py)；多个本地线程同时计算相同文件摘要，希望一次计算后复用。
- **原版现状／替代**：functools缓存线程安全但可能同键重复计算；无singleflight入口。
- **交付与模块**：新增同步singleflight包装，以每键in-flight状态等待，成功共享结果且失败传播并清理。；`src/wrapt/caching.py`、`src/wrapt/synchronization.py`。
- **兼容边界**：与结果缓存分开，可无长期缓存；不同键不互相串行；不运行网络任务。
- **正常验收**：多线程同键真实函数仅执行一次，不同键可并行。
- **异常／边界验收**：同线程递归同键、异常、取消等待、容量清理与用户key异常。
- **原生回归**：`tests/core/test_lru_cache.py`、`tests/core/test_synchronized_lock.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 08．同步到异步桥可选择执行器并传播上下文

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/synchronization.py)；CPU/本地阻塞函数进入async应用时要用指定线程池且保留ContextVar。
- **原版现状／替代**：sync_to_async固定run_in_executor(None,partial)，无executor参数与copy_context。
- **交付与模块**：增加executor/context参数或factory，明确取消只停止等待而不强杀线程函数。；`src/wrapt/synchronization.py`。
- **兼容边界**：默认现有行为可保留；不改变mark_as_async仅标记而不转换的作用。
- **正常验收**：指定线程池实际被使用，ContextVar值按策略到达计算函数。
- **异常／边界验收**：关闭executor、取消/异常、嵌套loop、generator仍按原规则拒绝及context隔离。
- **原生回归**：`tests/core/test_synchronized_markers.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 09．同步包装可明确设置获取锁预算

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/synchronization.py)；本地桌面任务忙时希望立即返回busy或在短预算后失败。
- **原版现状／替代**：synchronized仅一个wrapped参数；可传自定义lock，但无标准timeout/nonblocking策略。
- **交付与模块**：新增显式acquire配置，统一线程和async锁的超时结果与清理。；`src/wrapt/synchronization.py`。
- **兼容边界**：默认等待行为保持；自定义lock若不支持timeout明确拒绝；函数异常后仍释放锁。
- **正常验收**：忙锁nonblocking不进入函数，超时与成功可区分。
- **异常／边界验收**：取消等待、持锁者异常、可重入线程锁、async超时、错误lock协议与嵌套。
- **原生回归**：`tests/core/test_synchronized_lock.py`、`tests/core/test_synchronized_markers.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 10．按业务参数选择共享同步锁

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/synchronization.py)；不同实例处理同一product_id时需互斥，不同ID可并行。
- **原版现状／替代**：默认按实例/类/函数创建锁，或显式给一把锁；无keyed_synchronized。
- **交付与模块**：新增keyed_synchronized(key_fn,lock_factory)，受控管理每键锁并在无使用者时释放。；`src/wrapt/synchronization.py`、`src/wrapt/decorators.py`。
- **兼容边界**：默认synchronized作用域不变；锁键不是任意外部资源名，只是本地参数。
- **正常验收**：同ID跨实例串行，不同ID可并行，参数绑定正确。
- **异常／边界验收**：不可hash键、key异常、等待期间清理、递归、线程/async分开lock域。
- **原生回归**：`tests/core/test_synchronized_lock.py`、`tests/core/test_decorators.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 11．property装饰可同时管理读写删除访问器

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/decorators.py)；普通模型的property读写都需要相同参数校验或上下文。
- **原版现状／替代**：AutoObjectProxy已有描述符dunder支持，但无wrap_property一体化accessor管理入口。
- **交付与模块**：提供property adapter分别包装fget/fset/fdel并保留doc、抽象标记和描述符绑定。；`src/wrapt/decorators.py`、`src/wrapt/proxies.py`、`src/wrapt/wrappers.py`。
- **兼容边界**：不重复计已有descriptor透传；未定义访问器保持原AttributeError。
- **正常验收**：读取/写入/删除分别触发正确wrapper，原property签名/说明保持。
- **异常／边界验收**：只读property、继承覆盖、抽象属性、cached_property差异和访问器异常。
- **原生回归**：`tests/core/test_decorators.py`、`tests/core/test_attribute_wrapper.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 12．生成器装饰覆盖整个消费生命周期

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/decorators.py)；本地数据生成器需要在首个next到close期间计时或释放资源。
- **原版现状／替代**：普通FunctionWrapper只包装生成器创建调用，AutoObjectProxy可透传迭代但无生命周期callback协议。
- **交付与模块**：新增generator_decorator，覆盖next/send/throw/close以及async生成器对应协议。；`src/wrapt/decorators.py`、`src/wrapt/wrappers.py`、`src/wrapt/proxies.py`。
- **兼容边界**：不在创建时提前消费生成器；保留StopIteration.value与抛出异常类型。
- **正常验收**：yield序列不变，正常完成和提前close均触发一次finally回调。
- **异常／边界验收**：send/throw、未开始close、异常、async取消、aclose和GC后清理。
- **原生回归**：`tests/core/test_function_wrapper.py`、`tests/core/test_nested_function.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 13．上下文管理器工厂可包装进入到退出

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/decorators.py)；由函数返回的本地资源上下文需要在真正进入/退出时增加行为。
- **原版现状／替代**：BaseObjectProxy已有__enter__/__exit__/async透传，decorator只围住工厂调用。
- **交付与模块**：新增contextmanager_decorator，明确factory/enter/exit阶段回调和异常抑制策略。；`src/wrapt/decorators.py`、`src/wrapt/wrappers.py`、`src/wrapt/synchronization.py`。
- **兼容边界**：不把已有上下文协议透传称缺失；用户原__exit__的抑制结果不能被默认覆盖。
- **正常验收**：成功/抛错/提前退出路径正确释放，sync与async均保留原with结果。
- **异常／边界验收**：enter失败、exit失败、嵌套复用、一次性manager、async取消和ExceptionGroup。
- **原生回归**：`tests/core/test_decorators.py`、`tests/core/test_object_proxy.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 14．提供可组合的调用前后与异常钩子协议

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/decorators.py)；本地函数完成后记录统计或校验结果，异常时另走处理。
- **原版现状／替代**：可手写四参数decorator，无统一call_hooks及跨同步/异步回调时机协议。
- **交付与模块**：增加CallHooks before/after/error/finally构造器，明确参数修改、结果替换与原异常传播。；`src/wrapt/decorators.py`、`src/wrapt/synchronization.py`、`src/wrapt/wrappers.py`。
- **兼容边界**：基础decorator保持；事件不自动保存所有参数，回调失败的错误合并规则清楚。
- **正常验收**：正常与异常顺序准确，async after发生在await完成后，绑定方法不丢self。
- **异常／边界验收**：before失败、finally失败、取消、回调返回None与未替换哨兵、嵌套wrapper。
- **原生回归**：`tests/core/test_decorators.py`、`tests/core/test_function_wrapper.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 15．参数适配器同时变更签名与真实调用

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/signature.py)；兼容旧quantity参数名到新count，展示签名和实际接收参数都要一致。
- **原版现状／替代**：with_signature明确只改内省不改calling behaviour；adapter也主要提供替代签名，真实参数由用户wrapper处理。
- **交付与模块**：新增argument_adapter声明rename/default/drop规则，bind后映射到真实函数并同步构造Signature。；`src/wrapt/signature.py`、`src/wrapt/decorators.py`、`src/wrapt/wrappers.py`。
- **兼容边界**：不把现有签名覆盖误称参数适配；冲突重命名和不支持结构在装饰时失败。
- **正常验收**：旧名/新名在声明范围调用正确，inspect.signature与实际允许参数一致。
- **异常／边界验收**：positional-only、kw-only、重复给值、classmethod、异步函数和注解。
- **原生回归**：`tests/core/test_with_signature.py`、`tests/core/test_adapter_kwonly.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 16．弃用装饰器在真实调用位置给出可控提示

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/decorators.py)；公共计算函数迁移参数时需要一次或按调用点发出DeprecationWarning。
- **原版现状／替代**：有with_doc和通用decorator，无deprecated入口。
- **交付与模块**：新增deprecated装饰器，支持版本/替代说明、category、调用点stacklevel与按策略去重。；`src/wrapt/decorators.py`、`src/wrapt/wrappers.py`。
- **兼容边界**：不改变函数结果或默认替换参数；异步提示的发出时机明确，尊重warnings过滤。
- **正常验收**：用户调用行显示正确位置，正常签名和method绑定保留。
- **异常／边界验收**：多层wrapper、同一调用点、类/静态方法、协程取消和generator开始消费时机。
- **原生回归**：`tests/core/test_decorators.py`、`tests/core/test_with_doc.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 17．命名wrapper可形成有序可配置的调用管线

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/decorators.py)；同一计算函数按验证、计时、结果转换的固定优先级组合多个wrapper。
- **原版现状／替代**：wrapper_chain/find_wrapper已经存在，能观察/查找链，没有WrapperPipeline组装和版本化配置。
- **交付与模块**：增加命名pipeline构造/替换配置，校验重复名与依赖顺序，原子生成新链。；`src/wrapt/decorators.py`、`src/wrapt/patches.py`、`src/wrapt/wrappers.py`。
- **兼容边界**：不重新计已有链查询/unwrap；只组合明确传入的本地函数，不自动发现模块。
- **正常验收**：顺序和enable规则固定，重配置后新调用使用新链，旧链可继续完成。
- **异常／边界验收**：依赖环、同名wrapper、构造异常、递归调用、异步标记和签名保持。
- **原生回归**：`tests/core/test_decorators.py`、`tests/core/test_find_wrapper.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 18．多个本地方法可成组安装并整体恢复

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/patches.py)；测试夹具为两个自有类方法临时加包装，安装第二个失败时恢复第一个。
- **原版现状／替代**：已有单目标scoped_function_wrapper、unwrap_object和安装元数据，无WrapperGroup。
- **交付与模块**：新增事务式WrapperGroup，先解析明确本地目标再安装，失败逆序恢复并校验原定义仍匹配。；`src/wrapt/patches.py`。
- **兼容边界**：不研究第三方模块或网络入口；不把单目标已有scope称缺失；并发外部修改需冲突报告而非覆盖。
- **正常验收**：两个自有方法进入scope被包装，退出后原描述符和继承阴影完全恢复。
- **异常／边界验收**：第二项失败、嵌套group、重复目标、用户主动改属性、缺失目标和异常恢复。
- **原生回归**：`tests/core/test_unwrap_object.py`、`tests/core/test_transient_function_wrapper.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 19．代理复制和序列化采用显式状态策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/wrappers.py)；自定义本地数据代理需要选择复制包装器本身或复制底层值。
- **原版现状／替代**：基类__copy__/deepcopy/reduce有意NotImplementedError，用户必须每个子类重写。
- **交付与模块**：提供可选ProxyCopyPolicy及命名显式codec辅助，分别处理wrapped与wrapper-local状态。；`src/wrapt/wrappers.py`、`src/wrapt/_wrappers.c`、`src/wrapt/proxies.py`。
- **兼容边界**：不默认pickle任意callable/锁/生成器；现有要求显式策略保持，不把不支持称产品缺陷。
- **正常验收**：支持的简单代理按shallow/deep策略保留类型和本地状态，原底层对象共享规则可验证。
- **异常／边界验收**：循环图、weakref、C/Python一致、不可序列化资源、未知codec和自定义__wrapped_get__。
- **原生回归**：`tests/core/test_copy.py`、`tests/core/test_pickle.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

## 20．提供函数绑定与包装层的结构化诊断报告

- **类型／来源与场景**：enhancement；[来源](https://github.com/GrahamDumpleton/wrapt/blob/6b4e844950213118b19e613248d2bc9469eb731e/src/wrapt/wrappers.py)；维护者排查嵌套装饰后self/cls/签名来源。
- **原版现状／替代**：已有inspect.signature和wrapper_chain可组合，没有binding_report统一可读报告。
- **交付与模块**：新增只读报告列出各层真实类型、绑定类别、原函数/adapter签名来源与calling convention。；`src/wrapt/wrappers.py`、`src/wrapt/decorators.py`、`src/wrapt/signature.py`、`src/wrapt/patches.py`。
- **兼容边界**：不执行目标函数或触发不必要LazyObjectProxy初始化；报告中不自动展开业务参数和值。
- **正常验收**：普通/绑定/class/static方法给出正确绑定与原始签名，报告不改变调用结果。
- **异常／边界验收**：部分初始化代理、循环wrapped链、动态属性异常、过深链和async marker覆盖。
- **原生回归**：`tests/core/test_function_wrapper.py`、`tests/core/test_with_signature.py`、`tests/core/test_callable_binding_no_args.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；默认构建可选C扩展。测试pytest与上游CI固定mypy1.20.1；用等价CLI shim提供容器内mypy命令并将缓存放/tmp，源码/测试未改。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
