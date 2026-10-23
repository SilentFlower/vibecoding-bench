# Funcy 二十步迭代研究路线

固定[Suor/funcy@e8febffd57f80db8ca3a55fb1edd0feee2290d61](https://github.com/Suor/funcy/tree/e8febffd57f80db8ca3a55fb1edd0feee2290d61)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已有monotonic TTL cache、key_func、invalidate/invalidate_all、SkipMemory、位置/关键字缓存键隔离、once_per不可hash参数、retry动态timeout/filter_errors、reraise cause、lzip(strict)、滑动step与短尾chunks、get_lax/get_in/set_in/del_in、Call posonly/kwonly、list/惰性族均不重复计入。

## 01．autocurry不吞掉业务函数内部TypeError

- **类型／来源与场景**：bug_fix；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/funcs.py)；已给足必填参数的业务函数真正失败时，调用者应看到错误。
- **原版现状／替代**：带可选参数函数内部抛TypeError，autocurry(1)实跑返回另一个函数；req_n路径用try调用并把所有TypeError都当缺参数。
- **交付与模块**：在调用前用签名/Spec判断是否可绑定；只为未满足参数返回局部应用，真正调用后的异常直接传播。；`funcy/funcs.py`、`funcy/_inspect.py`。
- **兼容边界**：保留可选参数与分阶段调用习惯；内建函数签名未知时明确受限策略，不靠吞异常猜。
- **正常验收**：业务TypeError保持原异常/cause，真正参数不足仍得到可继续调用的函数。
- **异常／边界验收**：positional-only、keyword-only、varargs/varkw、bound方法、builtin和部分应用。
- **原生回归**：`tests/test_funcs.py`、`tests/py38_funcs.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 02．缓存属性按实际描述符名称存储

- **类型／来源与场景**：bug_fix；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/objects.py)；把calculate方法显式暴露成value缓存属性时，应该只计算一次。
- **原版现状／替代**：value=cached_property(calculate)实跑两次读取1/2，数据缓存到calculate键并遮蔽原方法；使用fget.__name__而非绑定属性名。
- **交付与模块**：通过__set_name__记录实际属性名，cached_property/cached_readonly共用正确缓存键，处理旧Python回退。；`funcy/objects.py`。
- **兼容边界**：普通@cached_property名字相同路径保持；同一描述符绑定不同名字时拒绝或独立存储规则明确。
- **正常验收**：value两次读均1，calculate方法仍可正常访问，实例间缓存独立。
- **异常／边界验收**：继承/覆盖、别名重用、手动赋值/删除、readonly与无__dict__对象的明确错误。
- **原生回归**：`tests/test_objects.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 03．为协程提供已完成结果缓存

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/calc.py)；本地异步转换函数同参数可以多次await得到相同值。
- **原版现状／替代**：同步memoize缓存协程对象，实跑第二次await RuntimeError；没有amemoize。
- **交付与模块**：新增独立amemoize/acache协议，缓存await成功值并定义异常/取消/未完成状态。；`funcy/calc.py`、`funcy/decorators.py`。
- **兼容边界**：不将现有同步缓存返回对象的语义叫缺陷；默认memoize保持轻量。
- **正常验收**：同参数重复await成功，TTL版本用同样失效规则且各实例/loop边界明确。
- **异常／边界验收**：取消、异常、不同事件循环、同键并发、SkipMemory结果和清理。
- **原生回归**：`tests/test_calc.py`、`tests/test_decorators.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 04．TTL缓存可配置容量和主动清理策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/calc.py)；本地长期进程不断遇到新数据键，不希望过期键一直占据memory。
- **原版现状／替代**：cache已有monotonic TTL与expiry队列，无maxsize；写入和缺失访问不会普遍扫掉所有旧键。
- **交付与模块**：新增可选容量淘汰和按写入/周期触发的过期清理，提供可注入clock便于验证。；`funcy/calc.py`。
- **兼容边界**：现有timeout/key_func/invalidate/SkipMemory行为保持；不重复实现已存在TTL/单调时钟。
- **正常验收**：固定假时钟和容量下过期项清理、LRU或声明策略淘汰，结果仍正确。
- **异常／边界验收**：重复键旧expiry记录、TTL0/负、全部过期、手动失效、clear及内存上限。
- **原生回归**：`tests/test_calc.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 05．缓存可按实例管理并随实例释放

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/calc.py)；轻量不可hash业务对象的方法希望独立缓存，且对象结束后不被缓存保留。
- **原版现状／替代**：memoize为装饰函数共用memory，默认key包含self并要求可hash，可能保留实例；可自写descriptor。
- **交付与模块**：新增instance_memoize/cache descriptor，支持实例属性或弱引用存储并公开生命周期管理。；`funcy/calc.py`、`funcy/objects.py`。
- **兼容边界**：默认全函数memoize保持；不能让weak表的value通过bound方法反向强持有key。
- **正常验收**：两个不可hash实例同参数互不串值，删除实例后对应缓存可回收。
- **异常／边界验收**：slots、不可weakref、继承同名方法、GC循环和显式invalidate。
- **原生回归**：`tests/test_calc.py`、`tests/test_objects.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 06．缓存可按签名规范化等价调用

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/calc.py)；f(1)、f(x=1)和f(x=1,y=默认值)应按显式策略视作同一计算。
- **原版现状／替代**：已有key_func可手写；默认args与kwargs刻意隔离且kwargs顺序归一，未做完整Signature绑定。
- **交付与模块**：新增canonical_keys选项，bind/apply_defaults后生成键，并让invalidate严格复用同一算法。；`funcy/calc.py`、`funcy/decorators.py`、`funcy/_inspect.py`。
- **兼容边界**：默认旧键形状保持；不重提已修复的位置/关键字碰撞或kwargs顺序问题。
- **正常验收**：等价调用命中同项，invalidate任一等价形态都能删除。
- **异常／边界验收**：posonly/kwonly、varargs/varkw、不可hash默认值、自定义key_func优先级与签名变更。
- **原生回归**：`tests/test_calc.py`、`tests/test_decorators.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 07．once初始化可以选择成功后才标记完成

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/flow.py)；普通本地资源初始化首次暂未就绪，下一次需要重新尝试。
- **原版现状／替代**：once_per在执行前把参数放done集合；实跑首次ValueError后第二次noop且总调用1，符合当前仅调用一次的粗粒度语义。
- **交付与模块**：新增once state策略attempt/success及pending处理，成功后提交done，失败按策略清理。；`funcy/flow.py`、`funcy/decorators.py`。
- **兼容边界**：默认attempt语义保持或清楚迁移；不将全部首次失败必然重试作为原版承诺。
- **正常验收**：success模式失败后下次成功，之后noop；attempt模式仍只调用一次。
- **异常／边界验收**：并发、同线程递归、不同参数、不可hash参数、取消和重置状态。
- **原生回归**：`tests/test_flow.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 08．Call参数访问可支持partial和可调用对象

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/decorators.py)；通用decorator包装functools.partial或实现__call__的普通对象。
- **原版现状／替代**：arggetter/get_argnames直接用__code__；partial实跑AttributeError。_inspect.get_spec已有签名回退但两套未统一。
- **交付与模块**：统一Signature/代码快速路径，正确保留已绑定参数、posonly/kwonly和变参映射。；`funcy/decorators.py`、`funcy/_inspect.py`。
- **兼容边界**：普通函数快路径性能需按贡献规范测量；不执行被包装函数来猜签名。
- **正常验收**：partial(add,1)的b默认值正确，Call具名访问与inspect.bind一致。
- **异常／边界验收**：bound method、builtin无签名、callable实例、locals误当参数、wrapper.original和缓存生命周期。
- **原生回归**：`tests/test_decorators.py`、`tests/py38_decorators.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 09．本地计算重试可设置总预算并可取消

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/flow.py)；读取本地临时文件或计算任务时，单次重试间隔不能让总等待无限增长。
- **原版现状／替代**：retry已有tries、timeout(attempt)、errors和filter_errors；没有总budget、取消和sleep注入。
- **交付与模块**：新增RetryPolicy带max_elapsed/cancel/clock/sleep，返回明确终止原因或保留最终原异常。；`funcy/flow.py`。
- **兼容边界**：不重复提案已有回退间隔函数/异常过滤；只研究普通本地函数，不增加网络请求能力。
- **正常验收**：假时钟下总预算到达即停止，未匹配异常立即传播，tries仍是执行次数。
- **异常／边界验收**：tries0/负、长单次调用、sleep取消、callback异常、BaseException与最后异常cause。
- **原生回归**：`tests/test_flow.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 10．fallback可保留分支失败和明确无结果

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/flow.py)；三种本地格式解析器全失败时，需要区分没有结果和成功返回None。
- **原版现状／替代**：fallback逐分支catch后全失败返回None，无结构化Failure报告。
- **交付与模块**：新增可选FallbackResult/raise_all策略，记录分支索引与异常，明确成功None仍是成功。；`funcy/flow.py`。
- **兼容边界**：默认返回语义保持；不自动捕获未声明异常；不默认保存大对象输入。
- **正常验收**：一分支成功返回标记成功，全失败报告列出各已尝试异常。
- **异常／边界验收**：空approaches、成功None、错误元组、过滤异常、用户异常链和早停。
- **原生回归**：`tests/test_flow.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 11．上下文装饰支持新建资源和延迟执行生命周期

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/flow.py)；每次函数调用要创建新的contextmanager，生成器消费期间也需要资源保持打开。
- **原版现状／替代**：wrap_with接现成ctx，在函数返回generator前退出；实跑events为enter/exit/body，且单次generator context不可复用。
- **交付与模块**：新增ctx_factory及generator/async生命周期模式，将进入/退出绑定到真实执行期。；`funcy/flow.py`、`funcy/decorators.py`。
- **兼容边界**：现有wrap_with(ctx)普通函数契约保持；不默认复用单次资源，不吞原manager抑制策略。
- **正常验收**：每次调用获得独立scope，generator body发生在enter/exit之间，提前close也释放。
- **异常／边界验收**：enter失败、yield异常、throw/close、async取消、复用/重入和返回普通值。
- **原生回归**：`tests/test_flow.py`、`tests/test_decorators.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 12．树遍历输出路径和进入退出事件

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/tree.py)；本地嵌套配置查看器需要知道叶子完整路径，并可跳过某一子树。
- **原版现状／替代**：tree_nodes/leaves只有follow/children，输出值不带路径，无tree_walk。
- **交付与模块**：新增iterative tree_walk事件协议，含path/depth/node、pre/post与prune回调。；`funcy/tree.py`。
- **兼容边界**：保留现有nodes/leaves输出；默认不处理任意对象属性，只按调用者children。
- **正常验收**：嵌套dict/list输出准确键/索引路径，prune不访问被跳过子树。
- **异常／边界验收**：深树、空容器、共享节点、循环检测策略、children异常和顺序稳定。
- **原生回归**：`tests/test_tree.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 13．深层集合支持prewalk和postwalk重建

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/colls.py)；把嵌套订单所有金额转换单位，同时保留集合形状。
- **原版现状／替代**：walk只转换当前层，源码TODO列prewalk/postwalk；tree遍历只产值不重建。
- **交付与模块**：新增深层prewalk/postwalk，按显式container adapter重建并区分键/值变换。；`funcy/colls.py`、`funcy/tree.py`。
- **兼容边界**：默认不把字符串/bytes拆成子树；保持defaultdict工厂/Counter语义，输入不原地修改。
- **正常验收**：嵌套list/dict/tuple转换得到预期形状，前后序差异明确。
- **异常／边界验收**：空容器、键碰撞、共享对象、循环、不可变容器和转换后类型变化。
- **原生回归**：`tests/test_colls.py`、`tests/test_tree.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 14．嵌套映射可按业务冲突策略深合并

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/colls.py)；本地默认配置与用户覆盖合并时保留未覆盖的子键。
- **原版现状／替代**：merge为浅合并，样例a.x被a.y子dict整体覆盖；merge_with仅把同键值交给调用者。
- **交付与模块**：新增deep_merge显式mapping递归、sequence replace/append及冲突resolver，传完整路径。；`funcy/colls.py`。
- **兼容边界**：原merge保持浅层覆盖；不默认拼接所有列表或改变任意collection类型。
- **正常验收**：a.x/a.y都保留，冲突标量按声明选择，原输入不变。
- **异常／边界验收**：None与缺失、不同容器类型、defaultdict、循环输入、resolver异常和键顺序。
- **原生回归**：`tests/test_colls.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 15．嵌套路径更新可使用受支持的容器适配器

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/colls.py)；订单快照含tuple或自定义Mapping，需要复制更新并保持类型。
- **原版现状／替代**：update_in主要处理list和带.copy/get的dict；tuple嵌套实跑AttributeError。
- **交付与模块**：新增path adapter协议定义read/copy_set/delete/missing策略，内建tuple和Mapping适配。；`funcy/colls.py`。
- **兼容边界**：原list不自动扩容、dict自动建中间map的默认规则保持；类型转换必须显式。
- **正常验收**：tuple中dict更新返回新tuple，原嵌套值不变，旁支可共享。
- **异常／边界验收**：负索引、缺失路径、dataclass需显式适配、删除最后节点、不可写容器与错误路径定位。
- **原生回归**：`tests/test_colls.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 16．提供按键关联两份记录的关系连接

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/seqs.py)；本地订单行按sku匹配商品目录，输出全部需要的组合。
- **原版现状／替代**：merge/join合并集合，不是关系表join；没有join_by。
- **交付与模块**：新增join_by(left_key,right_key,how)，支持inner/left/full和稳定一对多结果，声明右侧物化成本。；`funcy/seqs.py`、`funcy/colls.py`。
- **兼容边界**：不能把重复键悄悄覆盖成一行；与现有group_by/group_values保持独立。
- **正常验收**：两份小表有重复SKU时生成正确笛卡尔匹配，left/full保留未匹配行。
- **异常／边界验收**：空表、None合法键、不可hash键策略、冲突字段、生成器异常和稳定顺序。
- **原生回归**：`tests/test_seqs.py`、`tests/test_colls.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 17．滑动窗口支持明确尾部填充和边界契约

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/seqs.py)；本地信号每4项一窗，最后不足可按常数补齐或保留。
- **原版现状／替代**：partition已经丢尾、chunks已经保留短尾，step也已有；没有fill尾部模式，负n/step在Sequence/iterator路径行为不一致。
- **交付与模块**：新增tail=drop/keep/fill与fillvalue/factory，统一验证正窗口与步长并保持惰性。；`funcy/seqs.py`。
- **兼容边界**：默认partition/chunks当前语义保持；不是把已有滑动step或短尾保留重新计数。
- **正常验收**：序列与单次迭代器同输入得到相同窗口；fill不足部分准确补齐。
- **异常／边界验收**：空输入、n1、step<n/==n/>n、非法参数、可变fill对象和不额外消费。
- **原生回归**：`tests/test_seqs.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 18．惰性分流可限制消费者落后缓冲

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/seqs.py)；同一普通数据流分成两路，一路长期不读时需要明确内存上限。
- **原版现状／替代**：split/split_at/split_by依赖itertools.tee，消费者失衡时缓冲可增长；无bounded_tee。
- **交付与模块**：新增bounded branching工具，设置max_lag及raise/drop/block受支持策略，并定义消费者close释放。；`funcy/seqs.py`。
- **兼容边界**：原tee型函数默认保持；同步单线程下block可能死锁，必须显式拒绝不支持组合。
- **正常验收**：落后超过阈值时按声明明确失败或丢弃，缓冲大小可验证。
- **异常／边界验收**：消费者提前close、空/单路、predicate只执行次数、源异常、重入和线程适用范围。
- **原生回归**：`tests/test_seqs.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 19．异步序列提供一致的惰性变换族

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/seqs.py)；本地async生成数据需要map/filter/chunks/reductions，保留同一函数式接口。
- **原版现状／替代**：现有map/filter返回同步map/filter，amap/afilter/achunks/areductions均不存在。
- **交付与模块**：作为一个完整交付增加async iterable核心族，支持明确sync/async回调及顺序/消费契约。；`funcy/seqs.py`、`funcy/funcmakers.py`。
- **兼容边界**：不自动把同步函数都丢线程池；默认顺序执行，不用同一个功能拆成多条凑数。
- **正常验收**：async生成器经过筛选分块与同步参考结果一致，首项不需物化全量。
- **异常／边界验收**：取消、aclose、回调异常、空流、慢消费者和可选受控并发。
- **原生回归**：`tests/test_seqs.py`、`tests/test_funcmakers.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

## 20．函数组合可声明命名阶段和失败上下文

- **类型／来源与场景**：enhancement；[来源](https://github.com/Suor/funcy/blob/e8febffd57f80db8ca3a55fb1edd0feee2290d61/funcy/funcs.py)；离线数据清洗由解析、规范化、校验组成，失败需知道阶段并可独立替换配置。
- **原版现状／替代**：compose/rcompose已有纯函数组合，无Pipeline阶段对象，错误只按普通调用栈传播。
- **交付与模块**：新增显式Pipeline，阶段有名称、输入/输出adapter和error policy，保持普通函数调用协议并可生成阶段报告。；`funcy/funcs.py`、`funcy/decorators.py`。
- **兼容边界**：原compose快速路径保持；不默认吞异常或保存全部业务数据；报告是可选运行结果。
- **正常验收**：配置的三个阶段按顺序执行，失败报告准确阶段且保留原cause。
- **异常／边界验收**：空阶段identity、重复名、配置无效、短路、可选async阶段与不可序列化callable。
- **原生回归**：`tests/test_funcs.py`、`tests/test_decorators.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；上游test_requirements固定pytest7.4.3与whatever0.7，已冻结。本轮复用已有成功venv和原生证据，没有重复安装或基线运行；新观察只用标准库。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
