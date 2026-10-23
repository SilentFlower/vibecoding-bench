# Injector 二十步迭代研究路线

固定[python-injector/injector@5daed12510fafc0bf73b6ef18d2884f78cd5e210](https://github.com/python-injector/injector/tree/5daed12510fafc0bf73b6ef18d2884f78cd5e210)。03/04/05/19为本提交已复现问题，其余16项为明确增强；全部未实施，验收是未来交付目标。
排除已存在auto_bind=False、ProviderOf、AssistedBuilder、Annotated保留与类构造inject支持；singleton身份的接口/多绑定症状合成一次交付。所有场景为普通本地对象装配。

## 01．子容器可显式扩展父容器多绑定

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/297)；插件集合在父配置给基础插件，子配置只追加本地插件。
- **原版现状／替代**：实跑父list为parent，子list只有child；_get_multi_binder只查自身绑定，不合并祖先。
- **交付和模块**：增加明确extend-parent多绑定模式，按父后子顺序合并并保留原覆盖模式。；`injector/__init__.py`。
- **兼容边界**：默认子覆盖行为保持，父列表/字典不被子修改；同源父贡献不能被重复合并。
- **正常验收**：父保持parent，启用扩展的子得到parent/child且独立兄弟子不受影响。
- **异常／边界验收**：多层继承、空父/子、作用域对象、子字典重复键策略、贡献顺序和迭代副作用。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 02．显式共享同一实现的singleton身份

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/298)；两个接口与多绑定贡献指向同一声明的共享对象时，希望使用同一个实例。
- **原版现状／替代**：实跑接口First/Second不同实例，重复multibind Shared也不同；SingletonScope按接口/伪key缓存。
- **交付和模块**：增加显式alias/shared-binding协议，接口别名和多绑定贡献引用同一规范绑定key；合并同源身份需求为一步。；`injector/__init__.py`。
- **兼容边界**：默认每绑定key缓存保持；不能将所有相同实现的不同参数绑定强行合并。
- **正常验收**：声明同一shared key后两个接口和两项贡献是同一对象，显式不同key仍独立。
- **异常／边界验收**：父子容器、scope覆盖、InstanceProvider、带参数BoundKey、循环alias与关闭资源次数。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 03．不解析明确排除注入参数的无关注解

- **类型／来源和场景**：bug_fix；[来源](https://github.com/python-injector/injector/issues/258)；调用方已经提供body且声明noninjectable，未知类型只用于应用静态说明。
- **原版现状／替代**：实跑传body仍_BindingNotYetAvailable；get_type_hints先处理整个callable，随后才过滤排除项。
- **交付和模块**：在求值前隔离非注入参数注解，独立获取真正需要注入的类型。；`injector/__init__.py`。
- **兼容边界**：需要注入的未知前向类型仍报错；不执行额外未知文本；返回注解现有忽略行为保持。
- **正常验收**：body为UnavailableType但显式给定时顺利返回given，其他依赖照常注入。
- **异常／边界验收**：NoInject/非注入decorator、kwargs/positional传值、未知返回类型、递归alias和装饰器顺序。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 04．BoundKey保留未显式提供参数的构造注入

- **类型／来源和场景**：bug_fix；[来源](https://github.com/python-injector/injector/issues/40)；只预设一个业务参数，其余构造依赖仍由容器解析。
- **原版现状／替代**：实跑BoundKey(Partial,value=...)缺prefix TypeError；代理最后直接interface(**kwargs)。
- **交付和模块**：将BoundKey剩余参数交给create_object/call_with_injection，已预设provider值优先。；`injector/__init__.py`。
- **兼容边界**：不让隐式默认覆盖显式值；不改变AssistedBuilder的现有类provider限制。
- **正常验收**：预设value=given且prefix成功注入，构造一次并输出item:given。
- **异常／边界验收**：嵌套BoundKey、非inject构造、位置参数、provider抛错、NoInject和已有默认值。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 05．类级noninjectable正确应用于dataclass构造

- **类型／来源和场景**：bug_fix；[来源](https://github.com/python-injector/injector/issues/169)；dataclass有服务依赖和必须由调用方给的value，类装饰器不能把value自动填0。
- **原版现状／替代**：实跑标记value非注入后仍得到0；noninjectable元信息保存在类，而inject转存到__init__。
- **交付和模块**：对类级装饰器将排除集合按正确顺序传播至最终构造方法。；`injector/__init__.py`。
- **兼容边界**：普通函数/方法装饰器保持；不存在参数仍UnknownArgument；不改dataclass本身生成字段规则。
- **正常验收**：未给value时明确缺参；additional_kwargs给value后保留该值且prefix注入成功。
- **异常／边界验收**：装饰器顺序、kw-only dataclass、继承/重写__init__、frozen和多个排除项。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 06．参数化泛型类具备明确的绑定解析策略

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/175)；Box[str]和Box[int]的依赖可按具体类型分别装配。
- **原版现状／替代**：实跑get(Box[str])为UnknownProvider，provider_for仅特判list/dict/ProviderOf等而不处理普通Generic alias。
- **交付和模块**：增加具体泛型类型变量替换与实例化策略，明确精确绑定、origin绑定和auto_bind的优先级。；`injector/__init__.py`。
- **兼容边界**：不把所有类型参数混到同一个singleton key；未绑定TypeVar不能静默当Any。
- **正常验收**：Box[str]的构造T解析为str，Box[int]使用int，精确实例覆盖优先。
- **异常／边界验收**：嵌套Generic、多参数、继承、约束TypeVar、partial specialization、forward refs和协议。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 07．受控作用域管理本地资源生命周期

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/251)；本地StringIO或临时格式器资源应在任务结束或异常时按逆序close。
- **原版现状／替代**：Provider只定义get，Injector无close/ExitStack入口；应用可手动管理contextmanager。
- **交付和模块**：新增显式resource provider和容器/作用域上下文，登记获得成功的资源并逆序释放。；`injector/__init__.py`。
- **兼容边界**：普通get不突然关闭对象；用户明确选择managed入口；不承诺回滚资源外部副作用。
- **正常验收**：两个本地资源进入顺序与关闭逆序可观察，正常/异常退出都只释放一次。
- **异常／边界验收**：构造中途失败、嵌套scope、重复singleton引用、清理异常聚合和未进入scope就get。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 08．异步provider可被异步解析入口等待

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/blob/5daed12510fafc0bf73b6ef18d2884f78cd5e210/injector/__init__.py)；async factory经过await才能返回普通格式器依赖，不能把coroutine当作注入实例。
- **原版现状／替代**：Injector只有同步get/call_with_injection，CallableProvider直接返回callable结果。
- **交付和模块**：增加aget/异步call协议，递归等待显式异步provider，并对同步入口误用清楚报错。；`injector/__init__.py`。
- **兼容边界**：同步provider和普通get保持；不在已有事件循环内隐式asyncio.run。
- **正常验收**：异步provider依赖同步值后实际await并返回对象，异步singleton并发只构造一次。
- **异常／边界验收**：取消、异常、异步递归环、同步入口拿到异步定义、多个独立解析和资源退出。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 09．ContextVar作用域隔离并发任务实例

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/162)；同线程两个asyncio任务分别处理本地作业，不能共享ThreadLocalScope缓存。
- **原版现状／替代**：公开只有NoScope/SingletonScope/ThreadLocalScope，可手写自定义scope；没有任务局部标准scope。
- **交付和模块**：新增显式进入退出的ContextScope，按ContextVar保存本次任务实例并恢复嵌套token。；`injector/__init__.py`。
- **兼容边界**：线程scope保持；任务继承和子任务复制策略明确，不使用进程全局可变缓存。
- **正常验收**：两个交错任务各复用自己的对象且彼此不同，退出后下一任务得到新对象。
- **异常／边界验收**：嵌套上下文、异常/取消退出、copy_context、线程、未进入scope请求及资源关闭。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 10．公开失效scope中一个或全部缓存对象

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/94)；本地配置更新后需要重建某个服务对象，不访问SingletonScope._context。
- **原版现状／替代**：Scope/SingletonScope/ThreadLocalScope没有clear/reset公共方法；可重建整个Injector。
- **交付和模块**：新增受限evict/clear协议，明确本线程/本context范围及资源释放策略。；`injector/__init__.py`。
- **兼容边界**：清缓存不修改绑定定义；不让一个线程无声清其他线程数据；已有外部引用不被强制销毁。
- **正常验收**：evict目标后下次get构造新对象，无关singleton仍为旧实例。
- **异常／边界验收**：不存在key、构造中、依赖对象是否级联、managed资源、子容器继承和清理异常。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 11．缺绑定时可选择使用参数默认值

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/118)；@inject构造参数str=backup在未配置时使用默认，配置后又可覆盖。
- **原版现状／替代**：auto_bind=False实跑UnsatisfiedRequirement，当前默认值不参与注入决策；NoInject只能永久禁用注入。
- **交付和模块**：增加opt-in default-fallback参数策略，只有真正无可用绑定时使用声明默认值。；`injector/__init__.py`。
- **兼容边界**：默认行为保持；provider存在但抛错不被当作缺绑定；auto_bind与显式默认优先级明确。
- **正常验收**：无str绑定用backup，显式绑定用configured，显式kwargs优先于二者。
- **异常／边界验收**：None/Optional、NewType、可变默认、默认工厂不在函数签名支持范围、provider失败和位置仅参数。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 12．显式预热已声明的eager singleton

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/44)；CLI应用希望启动完成前构造并验证明确指定的本地服务。
- **原版现状／替代**：Injector构造只安装模块，只有请求get才实例化；没有eager标记或预热入口。
- **交付和模块**：增加eager binding标记及显式initialize_eager，按已声明依赖构造并记录结果。；`injector/__init__.py`。
- **兼容边界**：不默认实例化所有可自动绑定类型；未调用initialize时仍惰性；失败停止并保留原异常链。
- **正常验收**：预热后首次业务get复用同一对象，计数证明仅构造一次。
- **异常／边界验收**：依赖顺序、循环、构造失败、重复预热、子容器及managed资源撤销。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 13．公开只读绑定快照及归属

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/111)；调试工具列出当前有效绑定、provider、scope和来自哪层容器。
- **原版现状／替代**：Binder只提供单项get_binding/has_binding，_bindings私有；get_binding还可能auto_bind生成新项。
- **交付和模块**：新增无副作用的bindings_snapshot，标注显式/隐式、父子覆盖和多绑定贡献。；`injector/__init__.py`。
- **兼容边界**：返回不可变副本，不暴露可改内部Binding；查看快照不能触发provider或auto_bind。
- **正常验收**：父子覆盖关系及各scope清楚可读，快照前后构造计数不变。
- **异常／边界验收**：空容器、特殊ProviderOf/AssistedBuilder、重复贡献、私有类型表示和绑定更新后的新快照。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 14．装配前静态检查可分析的依赖图

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/139)；本地批处理启动前一次发现缺少配置和明确循环，避免运行到一半才失败。
- **原版现状／替代**：auto_bind=False已提供严格缺绑定模式，不能重复计入；当前仍要实际get才能沿图发现问题。
- **交付和模块**：新增validate_graph(root_types)，从类/声明provider注解检查可见依赖，收集缺项/循环/无法分析的opaque节点。；`injector/__init__.py`。
- **兼容边界**：不执行构造或provider；不保证任意动态provider可静态判断；opaque必须明确标注。
- **正常验收**：两条独立缺依赖一次报告，静态环给完整类型路径且无构造副作用。
- **异常／边界验收**：forward refs、Optional/default策略、BoundKey、父子容器、动态provider和泛型。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；[13]。

## 15．结构化记录一次真实解析路径

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/167)；开发者需要知道某次get为何选择了父绑定和哪个scope，而非只看最后一个错误。
- **原版现状／替代**：当前只有debug日志和异常_stack文本，未提供trace/explain记录协议。
- **交付和模块**：新增显式trace上下文，记录请求/绑定来源/provider/scope缓存命中/返回或失败，不序列化业务实例。；`injector/__init__.py`。
- **兼容边界**：默认不收集；字段值默认不记录；不依赖日志字符串解析；错误cause保持。
- **正常验收**：一次正常get生成连贯父子解析事件，失败定位到真实缺失节点和参数。
- **异常／边界验收**：并发请求隔离、递归环、provider抛错、缓存命中、事件上限和监听器自身异常。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 16．测试可临时覆盖绑定并自动恢复

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/114)；单元测试临时用内存格式器替换服务，异常结束后恢复原绑定和恰当缓存。
- **原版现状／替代**：可手动binder.bind或建子容器，没有override上下文；直接覆盖可能留下已有singleton。
- **交付和模块**：新增明确override context，保存并恢复选定绑定及相应scope缓存，支持嵌套。；`injector/__init__.py`。
- **兼容边界**：不声称child injector等同临时替换原容器；不回滚用户对象内部已发生的修改。
- **正常验收**：上下文内取到替代值，退出/异常退出均恢复原绑定策略与按契约的原实例。
- **异常／边界验收**：嵌套同key、多key、managed资源、异步任务隔离、父绑定和已持有引用。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 17．每次根解析复用一组临时依赖

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/147)；创建A时A与其B依赖应共用同一C，下次创建另一个A又需要新C。
- **原版现状／替代**：NoScope每次新建，singleton跨根复用，ThreadLocalScope跨同线程复用；没有resolution scope。
- **交付和模块**：新增根解析作用域，嵌套get共享当前装配缓存，顶层解析完成自动丢弃。；`injector/__init__.py`。
- **兼容边界**：不同于任务ContextScope；一次任务可有多次根解析；ProviderOf延迟get的作用域时机明确。
- **正常验收**：同一个A和B看到相同C，第二次根A拿到不同C。
- **异常／边界验收**：嵌套显式get、异常清理、循环、异步根解析、重入provider和实例构造边界。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 18．字典多绑定重复key可显式拒绝

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/issues/234)；插件声明同名转换器时希望配置错误可见，不被后注册项覆盖。
- **原版现状／替代**：实跑dict多绑定x=1后x=2只得到2；MapBindProvider.get直接map.update。
- **交付和模块**：新增duplicate-key策略error/first/last，附贡献来源并复用父子合并配置。；`injector/__init__.py`。
- **兼容边界**：默认last保持；不同策略作用阶段明确，不把合法可覆盖配置突然判错。
- **正常验收**：error模式对重复x列出两个来源，first/last分别得到1/2。
- **异常／边界验收**：动态map provider、空映射、跨父子层、非str合法键、相等key和构造异常。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 19．Module类安装兑现构造参数注入

- **类型／来源和场景**：bug_fix；[来源](https://github.com/python-injector/injector/blob/5daed12510fafc0bf73b6ef18d2884f78cd5e210/injector/__init__.py)；模块类构造需要已绑定的本地Prefix，文档允许通过注入使其可实例化。
- **原版现状／替代**：Binder.install文档说模块类期望参数需被注入，实际直接module()；实跑NeedsConfig缺prefix TypeError。
- **交付和模块**：用容器create_object装配Module类，再执行模块安装，保留传入模块实例和配置函数。；`injector/__init__.py`。
- **兼容边界**：不能在模块构造中依赖它尚未声明的绑定；显式实例不再二次构造。
- **正常验收**：先绑定Prefix再install(NeedsConfig)成功且configure使用相同前缀。
- **异常／边界验收**：模块自身循环依赖、构造/配置异常、未@inject参数、父容器绑定和模块重复安装策略。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

## 20．模块配置可选择原子安装

- **类型／来源和场景**：enhancement；[来源](https://github.com/python-injector/injector/blob/5daed12510fafc0bf73b6ef18d2884f78cd5e210/injector/__init__.py)；一个配置模块先声明str再失败，调用方希望没有半套绑定残留。
- **原版现状／替代**：实跑binder.install(config)抛错后str显式绑定仍存在；当前逐项直接写_bindings。
- **交付和模块**：新增atomic_install模式，在暂存绑定计划通过后统一应用，失败丢弃本模块声明。；`injector/__init__.py`。
- **兼容边界**：普通install保持即时语义；无法撤销用户配置函数的任意外部副作用，必须说明。
- **正常验收**：配置失败后目标绑定表与安装前一致；成功模块一次提交可见。
- **异常／边界验收**：覆盖已有key、多绑定追加、嵌套模块、provider元数据校验失败、scope缓存及并发安装互斥。
- **原生回归**：`injector_test.py`、`injector/__init__.py`、`README.md`。
- **实际依赖／步骤依赖**：Python标准库inspect/typing/contextlib/threading/asyncio/contextvars；生产requirements.txt为空。测试仍用冻结pytest/pytest-cov/typing-extensions。；无。

未来在同一真实工程累计实现，各步包括测试/文档/失败修复，不拆矩阵计数。控制端冻结正反例、核对候选加载路径、实际实例身份/调用/本地资源释放，并回归原生含doctest与90%coverage门槛及此前能力。当前尚未冻结这些新增验收。
