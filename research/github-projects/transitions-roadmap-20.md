# Transitions：二十步真实工程迭代路线

固定 [pytransitions/transitions@bd42b38f3627e6bca7274fb4d9af2e105f75da7c](https://github.com/pytransitions/transitions/tree/bd42b38f3627e6bca7274fb4d9af2e105f75da7c)，见[单仓审查](./transitions.md)。3项原版复现修复与17项增强，均未实施；新API名称为拟议契约。

已读并排除层级/并行状态、final、Enum、internal/reflexive/wildcard迁移、may检查、queued处理、Async/Locked组合、Timeout/AsyncTimeout/Retry、Markup/pickle、模型代码生成、Mermaid/Graphviz当前与上一状态显示。不同结果报告、队列接收上限与待执行控制各是独立可验收能力，未拆代码/测试/文档凑步。

## 01．Markup保留正确的全局after回调

- **类型与场景**：复现修复提案；本地订单流程配置导出后重新加载，必须保留前后回调各自语义。
- **原版证据**：before=before_pack/after=after_pack的Markup导出中，after_state_change实际也变成before_pack；源码两行均遍历before_state_change。
- **交付目标**：导出after_state_change时读取实际after列表，核对配置往返及代码生成使用同一正确结果。
- **真实模块**：transitions/extensions/markup.py、transitions/experimental/utils.py。
- **兼容边界**：已有Markup能力不当新增；回调表示方式、顺序和空列表保持。
- **正常验收**：导出前后列表分别保留before_pack和after_pack，重新构造后执行一次对应回调。
- **边界验收**：只有before/只有after、多个/无回调、callable引用、层级Markup和生成base model不混淆。
- **原生回归**：tests/test_markup.py、tests/test_experimental.py。
- **实际依赖**：无；现有Markup协议。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/markup.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/experimental/utils.py)。

## 02．State对象列表的迁移删除

- **类型与场景**：复现修复提案；本地编辑器通过选定State对象批量移除订单事件路径。
- **原版证据**：remove_transition(source=[State draft])后pack仍剩1项；同一State单值删除后为0。源码hasattr错误检查整个容器。
- **交付目标**：对listify后的每个元素按State/Enum名称规范化，统一source与dest列表过滤。
- **真实模块**：transitions/core.py。
- **兼容边界**：字符串、单State、Enum及通配规则保持；列表元素按既有listify路径处理，未知/空选择不误删。
- **正常验收**：State对象列表正确移除匹配路径，其他source/dest仍保留。
- **边界验收**：混合名称/State/Enum、多个source/dest、最后一路径移除后的模型绑定、空列表和不存在trigger回归。
- **原生回归**：tests/test_add_remove.py、tests/test_core.py、tests/test_enum.py。
- **实际依赖**：无；现有状态对象。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/issues/750)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)。

## 03．不消耗调用者配置中的models

- **类型与场景**：复现修复提案；同一内存配置先生成模型代码，再创建两个独立流程实例。
- **原版证据**：MarkupMachine(markup=config)和generate_base_model(config)都会pop调用者models键，观察后两份原输入都丢键。
- **交付目标**：读取/复制配置后再做内部移除和派生字段更新，使配置消费者不就地破坏调用者映射及其models列表。
- **真实模块**：transitions/extensions/markup.py、transitions/experimental/utils.py。
- **兼容边界**：不深拷贝任意模型/回调对象；内部缓存可保持可变，但与调用方容器明确隔离。
- **正常验收**：多次生成/构造后原配置结构和值仍相同，每次仍获得同一models描述。
- **边界验收**：空models、nested children、共享子列表、异常构造、不可复制回调对象与read-only Mapping支持范围明确。
- **原生回归**：tests/test_markup.py、tests/test_experimental.py。
- **实际依赖**：无；标准库浅层容器复制；必要嵌套层逐层复制。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/markup.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/experimental/utils.py)。

## 04．条件失败的结构化诊断

- **类型与场景**：增强提案；本地订单界面需要解释缺库存或未完成打包时为何不能发货。
- **原版证据**：may_pack为bool False，无explain入口；现有conditions仅返回真值并在失败时短路。
- **交付目标**：增加显式诊断结果，含候选路径、规则标识、pass/fail/skipped/error和可选业务消息，保持默认bool入口。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：默认不额外执行被短路的有副作用规则；完整诊断只在声明纯规则或显式选择时评估更多项。
- **正常验收**：失败规则有稳定标识/原因，尚未执行规则标skipped，bool结果与真实触发一致。
- **边界验收**：unless反向规则、多候选路径、规则抛错、prepare改变条件、异步和层级来源回归。
- **原生回归**：tests/test_core.py、tests/test_async.py、tests/test_nesting.py。
- **实际依赖**：无；现有Condition/EventData扩展，不依赖第三方验证库。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/issues/733)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 05．无回调副作用的结构预览

- **类型与场景**：增强提案；本地流程编辑器要展示当前事件候选目标，不能为了显示按钮执行业务prepare。
- **原版证据**：may_pack实际调用prepare计数1但state仍draft；get_transitions已有结构查询，却无合成预览。
- **交付目标**：新增结构预览入口，返回候选source/dest、规则和回调描述，完全不执行prepare/guard；可运行性标unknown而非伪造True。
- **真实模块**：transitions/core.py、transitions/extensions/nesting.py。
- **兼容边界**：现may_*继续执行既有准备/条件；结构预览与步骤04真实条件诊断分开，不承诺未知规则的结果。
- **正常验收**：预览后计数/模型状态不变，可读候选目标与需要评估的条件。
- **边界验收**：internal/reflexive/wildcard、多个父层候选、并行状态、无事件和未知目标明确列出。
- **原生回归**：tests/test_core.py、tests/test_nesting.py、tests/test_parallel.py。
- **实际依赖**：无；只读已有状态图；不依赖步骤04。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/nesting.py)。

## 06．排队事件的最终结果凭据

- **类型与场景**：增强提案；本地串行订单队列需要区分已接收与条件拒绝。
- **原版证据**：queued=True时guard=False的pack仍返回True，最终state=draft；这是文档明确的入队返回约定。
- **交付目标**：新增submit/receipt入口，分别记录accepted/pending/succeeded/rejected/failed/cancelled及最终source/dest/error，完成后可查询或await。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：旧trigger bool保持；不把队列True当BUG，不自动持久化或跨进程承诺交付。
- **正常验收**：入队成功但条件拒绝的receipt最终rejected，成功事件含实际目标。
- **边界验收**：嵌套入队、异常导致清队列、取消、同名多事件、模型移除和同步/async等待回归。
- **原生回归**：tests/test_core.py、tests/test_async.py。
- **实际依赖**：无；标准库状态记录/Future；独立于容量和历史记录。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 07．有容量上限的事件接收

- **类型与场景**：增强提案；本地批处理回调产生许多后续事件时需要控制积压。
- **原版证据**：队列是无界deque，queue_capacity构造参数ValueError，无显式接收上限。
- **交付目标**：新增可选容量及明确拒绝/等待策略，统计当前积压；同步回调内禁止会自锁的阻塞等待。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：默认无上限保持；不静默丢事件，正在执行项是否计入容量明确；不提供网络消息队列。
- **正常验收**：上限2时第三个待处理事件按声明拒绝或可等待，已接收两项顺序不变。
- **边界验收**：容量0/负值、重入、async每模型队列、取消等待、错误清理和满队列回调回归。
- **原生回归**：tests/test_core.py、tests/test_async.py。
- **实际依赖**：无；标准库deque/asyncio同步原语；不依赖步骤06，可单独返回接收结果。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 08．显式暂停与清理待处理事件

- **类型与场景**：增强提案；本地流程编辑器临时暂停消费，查看或取消尚未执行的订单操作。
- **原版证据**：无pause_events/pending_events/cancel_pending公开入口，当前队列在触发调用中自动排空。
- **交付目标**：新增opt-in队列控制器，暂停接收或消费、只读列出pending描述、按句柄取消及显式drain/resume；执行中事件单独处理。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：默认自动排空保持；暂停不回滚已执行回调，不暴露可任意修改的内部partial队列。
- **正常验收**：暂停后两个事件保持pending，取消一个再resume仅执行另一个且顺序正确。
- **边界验收**：空队列、重复cancel、当前执行项、异常后清理、模型移除、异步取消和重入死锁回归。
- **原生回归**：tests/test_core.py、tests/test_async.py。
- **实际依赖**：无；本地控制状态/句柄；可独立使用，不强制步骤06receipt实现。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 09．多模型分发的逐项结果

- **类型与场景**：增强提案；本地批量订单同一事件有的成功、有的被业务规则拒绝。
- **原版证据**：dispatch只返回AND合并的False；观察中一个model已packed另一个仍draft，调用者须另查每项状态。
- **交付目标**：新增dispatch_report，按稳定模型标识返回每项执行状态/结果/异常，可选继续收集错误或fail-fast。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：旧dispatch bool与现异常传播保持；不承诺跨模型事务或自动回滚成功项。
- **正常验收**：两个模型分别返回成功和拒绝，报告保留输入顺序，collect模式能继续处理后一项。
- **边界验收**：模型移除、回调抛错、未知trigger、异步部分取消、重名模型与空批次回归。
- **原生回归**：tests/test_core.py、tests/test_async.py。
- **实际依赖**：无；标准库结果记录；不依赖步骤06单事件凭据。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 10．配置图的静态一致性检查

- **类型与场景**：增强提案；本地流程编辑器保存前想一次知道未知目标、不可达节点与意外终止点。
- **原版证据**：定义missing_target到absent未立即失败，已有注释明确延迟检查；无validate_config聚合入口。
- **交付目标**：新增只读静态诊断，报告未知端点、初始配置、可达性和终止/循环提示，按严重度输出路径；不执行guard。
- **真实模块**：transitions/core.py、transitions/extensions/nesting.py、transitions/extensions/markup.py。
- **兼容边界**：延迟检查默认可保持；条件图只能保守分析，不把有环一律判错或将不可达近似当运行证明。
- **正常验收**：未知absent明确报错，正常draft->packed->done图通过，dead-end按配置规则提示。
- **边界验收**：internal/wildcard、层级并行、Enum、合法终态、动态添加状态和循环人工确认回归。
- **原生回归**：tests/test_core.py、tests/test_nesting.py、tests/test_parallel.py、tests/test_markup.py。
- **实际依赖**：无；标准库图遍历；不要求networkx。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/nesting.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/markup.py)。

## 11．配置批次的原子应用

- **类型与场景**：增强提案；编辑器一次应用多条迁移定义，某条无效时希望整批不留下半成品。
- **原版证据**：add_transitions先添加extra，再因trigger=state失败；extra仍保留。原API逐项写入，不是事务。
- **交付目标**：新增transactional配置批次，先验证和构建临时图/绑定计划，全部成功后发布；失败恢复原事件、状态和模型绑定。
- **真实模块**：transitions/core.py、transitions/extensions/nesting.py、transitions/extensions/diagrams.py。
- **兼容边界**：原逐项API保持；不承诺任意用户自定义类构造器的外部副作用回滚。
- **正常验收**：第二条错误后原图和模型方法集合未改，成功批次一次生效且图缓存刷新。
- **边界验收**：重复定义、自定义Transition异常、已绑定同名方法、图后端失败、多模型和层级合并回归。
- **原生回归**：tests/test_add_remove.py、tests/test_nesting.py、tests/test_graphviz.py。
- **实际依赖**：无；本地图/绑定计划；步骤10可复用但不是功能前置。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/nesting.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/diagrams.py)。

## 12．版本化的纯状态快照

- **类型与场景**：增强提案；本地订单进度只需保存少量状态数据并在已构建流程中恢复。
- **原版证据**：pickle存取完整Machine已实际成功，Markup也已有模型state描述；无独立snapshot/restore_state协议。
- **交付目标**：新增版本化JSON友好的状态快照，包含模型稳定ID、活动状态路径和明确选取的数据字段，绑定现有已核对配置恢复。
- **真实模块**：transitions/core.py、transitions/extensions/nesting.py、transitions/extensions/markup.py。
- **兼容边界**：不重复发明pickle/Markup序列化；不序列化函数代码/锁/运行协程，未知模型属性不自动导出。
- **正常验收**：快照后在同版本配置恢复draft/并行活动路径，不触发业务enter/exit除非显式选择。
- **边界验收**：未知版本/状态、缺模型ID、Enum、并行路径、额外字段、恢复中错误和未清队列策略明确。
- **原生回归**：tests/test_core.py、tests/test_markup.py、tests/test_parallel.py。
- **实际依赖**：无；标准库JSON数据结构；持久化文件由调用者负责。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/nesting.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/markup.py)。

## 13．活动模型状态的显式迁移计划

- **类型与场景**：增强提案；本地配置升级把packed重命名为prepared，需要先检查所有正在编辑的订单。
- **原版证据**：已有set_state和嵌套配置复用remap，不存在活动模型migrate_states批次计划。
- **交付目标**：新增状态映射计划/preview，将旧路径映射到新已存在路径，列出受影响模型并校验全部目标，显式应用。
- **真实模块**：transitions/core.py、transitions/extensions/nesting.py。
- **兼容边界**：不把既有复用remap当缺失；不自动猜rename，不默认执行enter/exit或任意业务数据迁移。
- **正常验收**：三模型的旧packed映射到prepared，预览不写入，全部目标有效后再应用。
- **边界验收**：未映射状态、并行/父子路径、Enum、多个旧态合并、模型已移除和执行时版本变化回归。
- **原生回归**：tests/test_core.py、tests/test_nesting.py、tests/test_parallel.py。
- **实际依赖**：无；显式映射与本地模型；不依赖步骤12，可直接对当前模型操作。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/nesting.py)。

## 14．有界的结构化执行历史

- **类型与场景**：增强提案；本地订单调试需要查看事件、规则结果、前后状态和失败阶段。
- **原版证据**：可人工用finalize_event收集结果，日志已有；无内建history/record_events聚合。
- **交付目标**：新增opt-in有界记录器/observer，输出事件序号、模型ID、阶段、结果及时间，不默认复制完整业务参数。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：日志和回调保持；默认关闭，observer不能悄悄改变业务结果；与持久化快照不同。
- **正常验收**：成功与guard拒绝各有一条完整记录，嵌套事件关联正确且容量到达后按规则截断。
- **边界验收**：异常/finalize异常、observer异常、取消、参数选择、并发排序、无限历史禁用与开销回归。
- **原生回归**：tests/test_core.py、tests/test_async.py。
- **实际依赖**：无；标准库记录与计时；不要求步骤04/06先完成，可记录已有EventData。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 15．可注入的本地定时调度器

- **类型与场景**：增强提案；本地定时订单流程测试希望推进逻辑时钟而非睡眠，也需要查询剩余时间。
- **原版证据**：Timeout与AsyncTimeout已有；同步实现直接threading.Timer，scheduler参数传到State后TypeError。
- **交付目标**：新增明确scheduler/clock协议，创建/取消deadline句柄、查询剩余时长，提供手动推进的本地实现供测试。
- **真实模块**：transitions/extensions/states.py、transitions/extensions/asyncio.py。
- **兼容边界**：默认真实Timer/asyncio行为保持；不重复新增timeout，绝对deadline与单调时钟范围需明确。
- **正常验收**：手动推进到阈值前不触发，达到后只触发一次；离开状态取消，模型间句柄独立。
- **边界验收**：零/负时长、重入、同刻多个deadline、回调再调度、取消竞态、模型移除和async清理回归。
- **原生回归**：tests/test_states.py、tests/test_async.py。
- **实际依赖**：无；标准库时钟/本地调度；不要求外部任务服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/states.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 16．异步回调的顺序同任务模式

- **类型与场景**：增强提案；本地async上下文资源要求多个回调在同一任务中顺序进入退出。
- **原版证据**：实际before回调轨迹first_start/second/first_end，三个current_task均不是触发者；await_all使用asyncio.gather。
- **交付目标**：增加显式callback执行模式：默认parallel，opt-in sequential在同一任务逐项await；条件执行策略单独声明。
- **真实模块**：transitions/extensions/asyncio.py。
- **兼容边界**：默认gather并发及组间阶段顺序保持；同任务模式不承诺所有并行状态路径都被强制串行。
- **正常验收**：sequential轨迹first_start/first_end/second，任务身份相同，parallel仍保持原模式。
- **边界验收**：同步/异步混合、回调异常、取消、嵌套触发、层级并行与条件短路策略回归。
- **原生回归**：tests/test_async.py、tests/test_parallel.py。
- **实际依赖**：无；标准库asyncio，观察夹具只用Event，无远程资源。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/issues/717)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 17．按签名选择回调参数

- **类型与场景**：增强提案；商品事件携带quantity与note，但部分回调只关心quantity。
- **原版证据**：send_event=False会把全部kwargs转发；quantity_only收到多余note抛TypeError，现send_event=True为完整EventData替代。
- **交付目标**：增加opt-in签名参数绑定，按声明注入业务kwargs及明确的event/source/target上下文，缺参在运行前给清楚诊断。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py。
- **兼容边界**：旧完整转发和EventData模式保持；上下文名与业务同名时定义优先级，不静默丢必需参数。
- **正常验收**：quantity_only只接收quantity，同事件另一回调可接收note，默认模式仍原行为。
- **边界验收**：positional-only、kw-only、*args/**kwargs、默认值、bound method/partial、不可内省callable和async回归。
- **原生回归**：tests/test_core.py、tests/test_async.py。
- **实际依赖**：无；标准库inspect.signature；不依赖注入框架。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/issues/714)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)。

## 18．可声明的业务异常路径

- **类型与场景**：增强提案；本地打包回调失败时希望流程显式进入needs_review，并能在图中看到该路径。
- **原版证据**：on_exception已存在且可自写处理；error_dest参数传到Transition后TypeError。
- **交付目标**：新增显式错误路径声明，按异常类型和发生阶段匹配目标，保留原异常及处理结果，定义after失败时的来源状态。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py、transitions/extensions/markup.py、transitions/extensions/diagrams.py。
- **兼容边界**：默认异常传播/on_exception策略保持；不承诺回滚任意业务副作用，on_enter之后失败已有状态保留规则须明确。
- **正常验收**：before业务错误进入needs_review，异常记录仍可见，正常路径不走错误路由且图导出包含声明。
- **边界验收**：on_exit/on_enter/after/finalize各阶段、错误处理再次失败、无限循环限制、取消异常与异步回归。
- **原生回归**：tests/test_core.py、tests/test_async.py、tests/test_markup.py。
- **实际依赖**：无；本地异常类型匹配；不依赖步骤14记录器。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/issues/730)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)；[来源4](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/markup.py)；[来源5](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/diagrams.py)。

## 19．模型解绑与流程关闭生命周期

- **类型与场景**：增强提案；本地编辑器关闭订单对象后，需要移除机器安装的方法并释放定时器引用。
- **原版证据**：remove_model文档明确保留先前trigger方法；观察models已空但pack/trigger绑定仍在，无dispose入口。
- **交付目标**：新增显式detach(clean_bindings=True)/dispose协议，只移除本机器拥有且仍指向原绑定的方法，取消相关待处理项/定时器。
- **真实模块**：transitions/core.py、transitions/extensions/asyncio.py、transitions/extensions/states.py、transitions/extensions/locking.py。
- **兼容边界**：旧remove_model保持；不删除调用者后来覆写的方法，不声称Python循环引用本身就是泄漏。
- **正常验收**：干净detach后本机绑定消失，用户原方法与另一个机器的方法保留，重复dispose安全。
- **边界验收**：同一模型多机器/属性名、覆写绑定、运行中事件、锁上下文、timeout取消和弱引用可释放回归。
- **原生回归**：tests/test_add_remove.py、tests/test_states.py、tests/test_async.py、tests/test_threading.py。
- **实际依赖**：无；所有权记录与标准库清理；可独立记录本机资源，不依赖队列控制新API。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/issues/690)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/core.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/asyncio.py)；[来源4](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/states.py)；[来源5](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/locking.py)。

## 20．累计事件覆盖率的图形叠加

- **类型与场景**：增强提案；本地流程演示希望看到整个演练中走过哪些路径及次数。
- **原版证据**：GraphMachine/Mermaid已有active/previous状态样式，实际输出只有当前与上一状态；无transition_coverage累计入口。
- **交付目标**：新增opt-in按稳定迁移标识累计次数的coverage记录和图形叠加，可重置/导出，区分候选拒绝与成功路径。
- **真实模块**：transitions/extensions/diagrams.py、transitions/extensions/diagrams_base.py、transitions/extensions/diagrams_mermaid.py、transitions/extensions/diagrams_graphviz.py。
- **兼容边界**：现有get_graph/previous/ROI默认保持；不把已有图生成当新增，不依赖联网渲染。
- **正常验收**：演练两次成功路径显示计数2，未走路径0，reset后清空；Mermaid与Graphviz数据含义一致。
- **边界验收**：多模型合并、并行/层级路径、同名事件多迁移、配置编辑后标识失效、拒绝/异常是否计入明确。
- **原生回归**：tests/test_graphviz.py、tests/test_mermaid.py。
- **实际依赖**：已有Graphviz可选运行时；Mermaid纯文本无需系统工具；可自订observer，不依赖步骤14。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/diagrams.py)；[来源2](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/diagrams_base.py)；[来源3](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/diagrams_mermaid.py)；[来源4](https://github.com/pytransitions/transitions/blob/bd42b38f3627e6bca7274fb4d9af2e105f75da7c/transitions/extensions/diagrams_graphviz.py)。

## 控制端冻结与累计回归

未来以合成订单模型和确定的本地回调调用真实Machine，验证状态、调用顺序/次数、队列最终结果、原配置与绑定所有权。async使用Event确定交错，时间用注入时钟，图输出先检查真实结构与标识再用可选本地后端渲染；不使用远程业务系统。每步累计关联原生回归。原生2923通过/291条件skip只证明当前适用集合，不能视为20步新契约或全部可选后端通过。冻结验收与产品接入尚未开始。
