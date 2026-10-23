# Python Statemachine：二十步真实工程迭代路线

固定 [fgmacedo/python-statemachine@ec5d8173f740b37941818df13727db9d64ef498d](https://github.com/fgmacedo/python-statemachine/tree/ec5d8173f740b37941818df13727db9d64ef498d)，见[单仓审查](./python-statemachine.md)。1项原版复现修复与19项增强；全部未实施，新API名为拟议契约。

真实原版已具备SCXML/JSON/YAML、复合/并行/深浅历史、eventless/done.state、invoke/timeout、延迟与取消、参数注入、异步Future、pickle、图与schema校验，全部排除新增。后半路线针对明确的UML运行语义，而不是给已有功能换名；原PSSM缺口保留xfail，不当作已通过。

## 01．多目标迁移的完整可达性验证

- **类型与业务场景**：复现修复提案；订单启动同时进入打包和开票两个区域的指定完成态。
- **原版证据**：真实Python Fork类ready.to([packing_complete,billing_complete])被判billing_complete不可达；graph.visit_connected_states只跟随transition.target首目标。
- **交付目标**：图遍历检查全部transition.targets，保留层级初始节点和祖先关系，校正可达性及终态路径分析。
- **真实模块**：statemachine/graph.py、statemachine/factory.py、statemachine/transition.py。
- **兼容边界**：多目标执行本身已存在；不把两个候选目标a.to(b,c)和单次多目标a.to([b,c])混淆。
- **正常验收**：原Fork定义可构造并在事件后两个目标同时激活，真正孤立节点仍被拒绝。
- **边界验收**：空目标/internal、重复目标、合法同并行域、未知/互斥目标、历史节点及循环图回归。
- **原生回归**：tests/test_multiple_destinations.py、tests/test_statechart_parallel.py、tests/test_configuration.py，保留原SCXML默认语义。
- **实际依赖**：无；现有图结构。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/705)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/graph.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/factory.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)。

## 02．版本化运行状态快照

- **类型与业务场景**：增强提案；本地订单编辑器保存活动分支与历史，再在同配置恢复。
- **原版证据**：pickle已实际保存/加载done态，history_values已存在；无snapshot公共协议。
- **交付目标**：新增JSON友好版本化快照，保存活动路径、深浅历史和显式选取的model字段，绑定已知配置无副作用恢复。
- **真实模块**：statemachine/statemachine.py、statemachine/configuration.py、statemachine/io/model.py。
- **兼容边界**：不是新增pickle或SCXML配置读入；默认不序列化回调/线程/任意对象，活动invoke/延迟事件恢复边界明确。
- **正常验收**：复合/并行各分支与历史准确恢复，恢复不重复执行enter/guard，下一正常事件结果一致。
- **边界验收**：未知版本/状态、过期配置、Enum、缺history、运行中invoke、延迟队列与不可JSON字段有明确处理。
- **原生回归**：tests/test_copy.py、tests/test_configuration.py、tests/test_statechart_history.py，保留原SCXML默认语义。
- **实际依赖**：无；标准库数据结构与JSON；存储后端由调用方提供。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/618)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/statemachine.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/configuration.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 03．面向模型字段的叶态存储适配

- **类型与业务场景**：增强提案；本地关系表或JSON记录希望复合流程状态存为单叶值，而非库容器。
- **原版证据**：CompoundOrder的model.state是OrderedSet(editing,draft)，json.dumps直接TypeError；可配置state_field已有。
- **交付目标**：新增可选state storage adapter，仅存原子叶值，按祖先关系重建完整configuration；并行使用明确叶值列表。
- **真实模块**：statemachine/configuration.py、statemachine/statemachine.py。
- **兼容边界**：原model.state表示保持默认；这是日常读写边界，与完整历史快照不同，不重复新增state_field。
- **正常验收**：复合状态模型写draft，读取能恢复editing+draft；并行两叶可用JSON列表存储。
- **边界验收**：父状态更名、多个叶冲突、未知值、setter异常、线程读缓存和空配置回归。
- **原生回归**：tests/test_configuration.py、tests/test_mixins.py、tests/test_threading.py，保留原SCXML默认语义。
- **实际依赖**：无；调用者适配器和标准库；不依赖步骤02快照。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/597)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/configuration.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/statemachine.py)。

## 04．具有作用域和生命周期的状态数据

- **类型与业务场景**：增强提案；本地表单编辑只在editing期间保存草稿与计数，离开后清理。
- **原版证据**：State(data={quantity:0})TypeError，现有业务值需人工放model；history_values是状态历史，不是变量存储。
- **交付目标**：新增显式state data声明、每次进入的factory、祖先查找/遮蔽规则及变更通知，退出按策略销毁。
- **真实模块**：statemachine/state.py、statemachine/statemachine.py、statemachine/engines/base.py、statemachine/engines/async_.py。
- **兼容边界**：原model属性不自动迁入；可变默认值不能在实例间共享；重入与history恢复数据策略显式。
- **正常验收**：两订单编辑草稿互不影响，子态可查祖先作用域，离开editing后仅清所属数据。
- **边界验收**：factory异常、空键/重名、类型检查、并行遮蔽、退出失败、重入与快照可选整合回归。
- **原生回归**：tests/test_state_callbacks.py、tests/test_statechart_compound.py、tests/test_callbacks_isolation.py，保留原SCXML默认语义。
- **实际依赖**：无；标准库容器/声明记录；不依赖存储库。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/661)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/statemachine.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)。

## 05．继承状态的结构细化

- **类型与业务场景**：增强提案；订单基础流程的packed在子类细化为picking/boxing，继承外部路径不重写。
- **原版证据**：RefinedOrder用同名复合态替换packed后InvalidDefinition，picking/boxing不可达；普通继承和复合态本身都已有。
- **交付目标**：每个派生类复制需要细化的图并按状态身份重连继承迁移到新态，保留事件、guard和callback。
- **真实模块**：statemachine/factory.py、statemachine/state.py、statemachine/transition.py。
- **兼容边界**：按明确新增组合能力处理，不把所有类继承当缺失；父类及兄弟类图和回调不可被就地改动。
- **正常验收**：父Order仍是单packed，RefinedOrder经过picking/boxing后沿原finish离开，兄弟类互不污染。
- **边界验收**：多重继承、同名事件、深层替换、显式value、history/parallel、冲突迁移和图复制所有权回归。
- **原生回归**：tests/test_statemachine_inheritance.py、tests/test_statechart_compound.py、tests/test_callbacks_isolation.py，保留原SCXML默认语义。
- **实际依赖**：无；图复制/重绑定；不先要求其他新状态构造。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/660)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/factory.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)。

## 06．明确的external/local/internal迁移类型

- **类型与业务场景**：增强提案；复合订单流需要清楚表达退出整个父态、仅重置子态或只执行动作。
- **原版证据**：Transition的kind参数TypeError；已有internal布尔和to(None)，语义随source而异。
- **交付目标**：新增三个显式kind，统一Python/native JSON/YAML/SCXML到内部迁移域规则，兼容期明确旧internal别名。
- **真实模块**：statemachine/transition.py、statemachine/engines/base.py、statemachine/io/model.py、statemachine/io/scxml/reader.py。
- **兼容边界**：旧internal默认语义在兼容期保持；kind与旧别名同时提供明确拒绝；不改变to(None)已有targetless能力。
- **正常验收**：同一复合态三类迁移有对应可核验exit/action/enter轨迹，格式读入结果一致。
- **边界验收**：atomic local非法、非后代目标、parallel local、self/internal目标校验、多个targets和别名冲突回归。
- **原生回归**：tests/test_transitions.py、tests/test_statechart_compound.py、tests/io/test_format_parity.py，保留原SCXML默认语义。
- **实际依赖**：现有PyYAML/jsonschema；更新既有native schema，无新外部服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/723)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/scxml/reader.py)。

## 07．异步原生timeout调用

- **类型与业务场景**：增强提案；本地async订单有很多等待态，希望不占用线程池等待定时器。
- **原版证据**：timeout(1)返回_Timeout，run不是coroutine，现有_has_async_run判False；源码threading.Event.wait等待。
- **交付目标**：提供async引擎专用async timeout handler，使用可取消async等待；同步引擎继续原线程等待。
- **真实模块**：statemachine/contrib/timeout.py、statemachine/invoke.py。
- **兼容边界**：timeout功能已存在且当前能用；只增加异步资源路径，duration单位继续秒，不能破坏同步handler。
- **正常验收**：async下大量pending timeout不提交长期executor等待，退出状态取消后不再发送expired。
- **边界验收**：超时恰好退出、重复进入、取消中处理、duration非法、done.invoke无on及同步兼容回归。
- **原生回归**：tests/test_contrib_timeout.py、tests/test_invoke.py、tests/test_async.py，保留原SCXML默认语义。
- **实际依赖**：无；标准库asyncio；不需要新调度服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/613)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/contrib/timeout.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/invoke.py)。

## 08．按状态停留时间声明的事件

- **类型与业务场景**：增强提案；订单进入waiting后30秒未完成则自动走expired路径，离开时撤销。
- **原版证据**：State(expire_after=1)TypeError；send(delay)和invoke=timeout已存在，不能再次列新增。
- **交付目标**：新增明确的状态时间迁移声明，构建于现timeout invoke，支持native描述与图标签，离开取消/重入重计时。
- **真实模块**：statemachine/state.py、statemachine/contrib/timeout.py、statemachine/io/model.py、statemachine/contrib/diagram/extract.py。
- **兼容边界**：避开已占用的after回调名字；不以同步callback内send(delay)假装非阻塞定时。
- **正常验收**：停留到阈值走expired，提前离开不触发，第二次进入有独立计时；图中可见时间规则。
- **边界验收**：零/负值、同刻业务事件、多个计时、嵌套父子时钟、final状态与async取消回归。
- **原生回归**：tests/test_contrib_timeout.py、tests/test_statechart_delayed.py、tests/io/test_native_behavior.py，保留原SCXML默认语义。
- **实际依赖**：复用现有timeout/invoke；步骤07为可选效率提升，不是必需前置。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/703)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/contrib/timeout.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/contrib/diagram/extract.py)。

## 09．显式的UML完成迁移

- **类型与业务场景**：增强提案；本地任务完成与普通无事件自动迁移需要分别表达。
- **原版证据**：completion关键字TypeError；已有done.state和eventless语义，原PSSM仍有K2等差异标记。
- **交付目标**：新增独立completion声明和事件调度规则，每个完成单独微步处理；native描述和图输出保留该语义。
- **真实模块**：statemachine/transition.py、statemachine/engines/base.py、statemachine/engines/sync.py、statemachine/engines/async_.py、statemachine/io/model.py。
- **兼容边界**：原SCXML eventless/done.state默认不变，不能将全部无事件迁移改成UML完成。
- **正常验收**：两个并行区域分别完成时以明确微步顺序处理，显式completion在两个基类都可用。
- **边界验收**：重复完成、重新进入、final父态、多完成竞争、错误事件和原W3C集合默认回归。
- **原生回归**：tests/test_statechart_eventless.py、tests/test_statechart_donedata.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；内部事件语义；是后续活动完成/延迟回放的明确前置。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/699)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)；[来源6](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 10．活动在进入时启动并参与完成判定

- **类型与业务场景**：增强提案；本地生成报价的活动未结束前，订单不能因空迁移自动跳到下一阶段。
- **原版证据**：invoke已有且同步引擎在macrostep末spawn_pending；无invoke_start_on_entry模式，K14/K2案例仍xfail。
- **交付目标**：增加opt-in UML活动时序，进入阶段启动，状态完成需等所属活动结束；默认SCXML宏步末启动保持。
- **真实模块**：statemachine/invoke.py、statemachine/engines/base.py、statemachine/engines/sync.py、statemachine/engines/async_.py。
- **兼容边界**：只改变显式所选语义，不破坏原invoke/cancellation；活动失败转error与结束信号分别定义。
- **正常验收**：受控本地Event活动阻塞时不走完成，活动结束后完成迁移，trace确认启动阶段正确。
- **边界验收**：同步立刻结束、多个活动、退出中取消、失败/重入、父子完成和默认SCXML回归。
- **原生回归**：tests/test_invoke.py、tests/test_error_execution.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：标准库线程/async事件；功能依赖步骤09显式completion。 功能步骤依赖：python-statemachine-09。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/700)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/invoke.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)。

## 11．活动等待并接收所属流程事件

- **类型与业务场景**：增强提案；本地复核活动需要等待订单的confirm输入，再继续工作。
- **原版证据**：InvokeContext已有send回父机，无receive入口；requires:do_activity_accept原生案例仍xfail。
- **交付目标**：新增活动receive/wait协议，仅在handler声明等待时转交匹配事件，明确同步/异步取消和与普通迁移的优先关系。
- **真实模块**：statemachine/invoke.py、statemachine/engines/base.py、statemachine/engines/async_.py。
- **兼容边界**：原ctx.send和SCXML子机通信不重复新增；未等待的活动不能吞掉正常状态事件。
- **正常验收**：活动等待confirm后收到一次payload，完成后父流程继续，普通无关事件仍按状态图处理。
- **边界验收**：多个等待者、匹配次序、退出取消、事件已被迁移消费、线程交接、超时与重复投递回归。
- **原生回归**：tests/test_invoke.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：标准库线程/async等待；依赖步骤10活动生命周期。 功能步骤依赖：python-statemachine-10。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/701)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/invoke.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)。

## 12．状态事件延后与按序回放

- **类型与业务场景**：增强提案；订单忙于pack时保留update，离开后再按规定顺序处理。
- **原版证据**：State(defer)TypeError；cancel_event已经能取消延迟事件，和业务defer不同；requires:defer案例仍xfail。
- **交付目标**：新增按状态声明的deferrable事件和recall队列，定义父子/并行归属及相对completion的回放顺序。
- **真实模块**：statemachine/state.py、statemachine/engines/base.py、statemachine/engines/sync.py、statemachine/engines/async_.py、statemachine/io/model.py。
- **兼容边界**：普通内部/外部队列和delay/cancel默认保持；defer不等于重新定时，也不悄悄丢事件。
- **正常验收**：busy中两次update延后，离开后按定义次序各处理一次，完成事件优先关系可复现。
- **边界验收**：重入再次defer、多个区域、final时待回放、取消、同ID事件、异常和无defer零开销回归。
- **原生回归**：tests/test_event_ordering.py、tests/test_cancel_event.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：标准库本地队列；依赖步骤09确定完成/回放相对顺序。 功能步骤依赖：python-statemachine-09。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/714)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)；[来源6](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 13．可复用子流程类的嵌入

- **类型与业务场景**：增强提案；订单的两个审核阶段复用同一子流程拓扑但拥有独立活动状态。
- **原版证据**：State(submachine=Order)TypeError；State(invoke=Order)已有包装，但它使用独立子机/队列，不是内联子状态。
- **交付目标**：新增将StateChart类嵌为compound state的能力，复制/前缀化图并按拥有者解析回调，保持父机同一运行语义。
- **真实模块**：statemachine/state.py、statemachine/factory.py、statemachine/transition.py。
- **兼容边界**：原invoke子机保持；两个嵌入不能共享State对象或历史；不自动支持连接点。
- **正常验收**：同类嵌两次可分别推进，一次完成不改变另一份，外部迁移与内联声明等价。
- **边界验收**：嵌套复用、显式value碰撞、callback继承、并行嵌入、循环嵌入拒绝与图导出回归。
- **原生回归**：tests/test_statemachine_inheritance.py、tests/test_statechart_compound.py、tests/test_callbacks_isolation.py，保留原SCXML默认语义。
- **实际依赖**：无；依赖步骤05的图复制/身份重绑定。 功能步骤依赖：python-statemachine-05。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/704)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/factory.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)。

## 14．按运行时项目列表创建并行区域

- **类型与业务场景**：增强提案；订单含可变数量的商品，每项经历相同处理子流程并在全部完成后合流。
- **原版证据**：State(regions_factory=...)TypeError，当前State.Parallel只接受静态states；现InvokeGroup并行callable不等于活动区域。
- **交付目标**：新增显式运行时区域工厂、稳定item ID与每项子图实例，集合完成屏障和事件路由由库管理。
- **真实模块**：statemachine/state.py、statemachine/configuration.py、statemachine/engines/base.py、statemachine/factory.py。
- **兼容边界**：静态Parallel默认保持；本步限定实例创建时确定列表，任意中途增删为后续范围，避免隐式修改共享类图。
- **正常验收**：0/1/3商品区域各按策略启动，每项独立推进，全部完成后父态只完成一次。
- **边界验收**：重复item ID、空集合、某项失败/取消、事件目标不明、快照ID、实例隔离和规模预算明确。
- **原生回归**：tests/test_statechart_parallel.py、tests/test_configuration.py、tests/test_invoke.py，保留原SCXML默认语义。
- **实际依赖**：无；复用本地图与实例；依赖步骤13可复用子图实例。 功能步骤依赖：python-statemachine-13。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/616)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/configuration.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/factory.py)。

## 15．junction节点与分段迁移动作

- **类型与业务场景**：增强提案；订单跨多个复合态边界的迁移需要确定退出、片段动作和进入的交错顺序。
- **原版证据**：State(kind=junction)TypeError；已有guarded分支和整微步执行，requires:junction案例仍xfail。
- **交付目标**：新增junction声明及分段executor，按选定路径执行各segment，并在格式描述中保留结构。
- **真实模块**：statemachine/state.py、statemachine/transition.py、statemachine/engines/base.py、statemachine/engines/sync.py、statemachine/engines/async_.py、statemachine/io/model.py。
- **兼容边界**：已有guarded选择保持；图渲染已有部分伪态形状不等于执行语义已支持，不能只画图算完成。
- **正常验收**：跨两层边界路径的完整动作trace与定义顺序一致，同步/异步相同。
- **边界验收**：多段guard失败、effect抛错、环路、父子边界、零目标、并行域和终结路径回归。
- **原生回归**：tests/test_transitions.py、tests/test_error_execution.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；新的本地分段执行结构；不依赖其他新节点。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/715)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源6](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)；[来源7](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 16．动作之后决策的choice节点

- **类型与业务场景**：增强提案；订单先计算金额再根据新金额选择普通或人工复核路径。
- **原版证据**：State(kind=choice)TypeError；cond守卫已有，requires:choice/junction原案例仍xfail。
- **交付目标**：新增动态choice伪态，第一段effect执行后再计算其出口guards，提供明确else分支。
- **真实模块**：statemachine/state.py、statemachine/transition.py、statemachine/engines/sync.py、statemachine/engines/async_.py、statemachine/io/model.py。
- **兼容边界**：不是重做已有按声明顺序guarded alternatives；新增的是中间动作后才选择的原子分段路径。
- **正常验收**：入口动作把total改到阈值后，选择看到新值，else只在其他条件不满足时运行。
- **边界验收**：多个true、无匹配/无else、guard副作用、异常、choice链/环、并行边界和原普通guard回归。
- **原生回归**：tests/test_multiple_destinations.py、tests/test_conditions_algebra.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；依赖步骤15分段executor。 功能步骤依赖：python-statemachine-15。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/716)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)；[来源6](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 17．跨区域的join同步节点

- **类型与业务场景**：增强提案；打包和开票两条并行路径分别到达合流点后共同进入发货。
- **原版证据**：State(kind=join)TypeError；静态parallel+done.state已有，requires:join案例仍xfail。
- **交付目标**：新增多source join域计算与到达屏障，全部required incoming满足后执行单次出段和effects。
- **真实模块**：statemachine/transition.py、statemachine/engines/base.py、statemachine/engines/sync.py、statemachine/engines/async_.py、statemachine/io/model.py。
- **兼容边界**：不重复已有父parallel完成；join必须定义合法区域来源，不能跨互斥分支静默等待永不完成。
- **正常验收**：两个区域到达后只执行一次发货动作，trace证明所有退出先于join效果。
- **边界验收**：重复到达、区域重入、任一路取消/失败、非法多source域、循环join和原done.state回归。
- **原生回归**：tests/test_statechart_parallel.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；依赖步骤09完成调度与步骤15分段域计算。 功能步骤依赖：python-statemachine-09、python-statemachine-15。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/718)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/transition.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)；[来源6](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 18．立即终止的terminate节点

- **类型与业务场景**：增强提案；本地流程明确取消全部工作时立即终止，不继续普通退出动作。
- **原版证据**：State(kind=terminate)TypeError；final/is_terminated和退出时取消invoke已存在，requires:terminate案例仍xfail。
- **交付目标**：新增terminate伪态，立即停止引擎、取消所属invoke/延迟项并解决等待结果，按UML模式不执行普通exit行为。
- **真实模块**：statemachine/state.py、statemachine/engines/base.py、statemachine/invoke.py、statemachine/io/model.py。
- **兼容边界**：普通final默认仍按现语义；明确仅terminate跳过exit，不把正常final改成强停。
- **正常验收**：进入terminate后本地活动被取消、后续事件不执行、exit计数仍0且终止标识明确。
- **边界验收**：嵌套/并行区域、终止中异常、待等待Future、重复终止、父子机边界和原final回归。
- **原生回归**：tests/test_statechart_donedata.py、tests/test_invoke.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；已有取消/stop机制扩展；不依赖其他新伪态。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/719)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/invoke.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 19．复合流程的入口和出口连接点

- **类型与业务场景**：增强提案；复用审核子流程时由不同入口进入不同步骤，并从指定出口回父流程。
- **原版证据**：State(kind=entry_point/exit_point)均TypeError；requires:entry_point/exit_point案例仍xfail，初始迁移与history已有。
- **交付目标**：新增成套entry/exit连接点，明确父子段动作顺序及复用子机连接映射，native定义和图保留节点。
- **真实模块**：statemachine/state.py、statemachine/factory.py、statemachine/engines/base.py、statemachine/io/model.py。
- **兼容边界**：不重复初始后代目标或history；入口/出口连接点只解决跨边界接口，不自动暴露任意子态。
- **正常验收**：快速入口进入review，出口完成后父流程动作与进入/退出顺序准确，两个复用实例连接互不干扰。
- **边界验收**：无连接、多个候选、parallel多个出口、错误域、深层嵌入、异常段和普通复合态回归。
- **原生回归**：tests/test_statechart_compound.py、tests/test_invoke.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；依赖步骤15分段执行；与步骤13结合时另测复用连接，但基础连接点可独立。 功能步骤依赖：python-statemachine-15。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/717)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/state.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/factory.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/base.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/io/model.py)。

## 20．具有回复语义的调用事件

- **类型与业务场景**：增强提案；本地同步调用订单reserve操作，需要等待实际处理后返回明确输出参数。
- **原版证据**：Event(reply=True)TypeError；普通send返回callback结果已实际得到quantity=2，async Future结果也已有；requires:call_event案例仍xfail。
- **交付目标**：新增显式call/reply事件契约，关联操作请求与回复，定义重入/跨线程等待、out参数和延后事件的返回时机。
- **真实模块**：statemachine/event.py、statemachine/event_data.py、statemachine/engines/sync.py、statemachine/engines/async_.py。
- **兼容边界**：不是新增普通事件返回值；避免同步运行线程等待自身；取消/终止时不留永久等待者。
- **正常验收**：另一个本地线程调用期间等候实际事件结果，返回对应请求回复，普通send结果保持。
- **边界验收**：多个调用、defer后回放、异常回复、取消、重入、自线程调用、out参数类型与异步Future兼容回归。
- **原生回归**：tests/test_async_futures.py、tests/test_threading.py、tests/uml/pssm/test_pssm_cases.py，保留原SCXML默认语义。
- **实际依赖**：无；标准库本地Future/线程；完整deferred call行为依赖步骤12。 功能步骤依赖：python-statemachine-12。
- **依据**：[来源1](https://github.com/fgmacedo/python-statemachine/issues/720)；[来源2](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/event.py)；[来源3](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/event_data.py)；[来源4](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/sync.py)；[来源5](https://github.com/fgmacedo/python-statemachine/blob/ec5d8173f740b37941818df13727db9d64ef498d/statemachine/engines/async_.py)。

## 冻结验收与累计回归

未来以合成本地订单/审核任务、线程Event和async Event验证真实状态配置、微步轨迹、回调次序、history、取消及回复。UML新语义以明确opt-in契约运行，既有W3C/原默认集合保持；每项新增契约不能仅靠删除xfail标记宣称通过，必须将对应原例的状态/轨迹/返回值独立固定。逐步累计关联原生回归及前置步骤。2810通过不意味着189skip/126xfail或20步提案已通过；冻结验收、制品准备和产品接入尚未开始。
