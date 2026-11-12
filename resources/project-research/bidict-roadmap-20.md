# Bidict 二十步迭代研究路线

固定[jab/bidict@299fedc89f1d70d5d41cf7922564b376d3e2d435](https://github.com/jab/bidict/tree/299fedc89f1d70d5d41cf7922564b376d3e2d435)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已支持OnDup三动作、可逐调用策略、原子putall/异常回滚、union、frozenbidict、可逆views、有序move_to_end/popitem、自定义backing mapping、Weakref和SortedBidict配方、动态inverse与pickle，不重复计为新增。

## 01．允许按最终唯一状态原子重分配键值

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；调换两个商品的标签而不丢任何键。
- **原版现状／替代**：putall按顺序检查即时冲突，a1/b2改a2/b1第一条就KeyAndValueDuplicationError；原表可靠回滚已存在。
- **交付与模块**：新增reassign批次，先验证完整目标状态唯一性，再原子替换受影响关系，支持循环置换。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_orderedbase.py`。
- **兼容边界**：不改变putall顺序策略；不采用forceupdate删除冲突项来伪装循环交换。
- **正常验收**：两项交换及三项循环保留所有键值，inverse和OrderedBidict位置按声明保持。
- **异常／边界验收**：目标重复、缺失键、生成器异常、相同对象、custom backing映射异常回滚。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 02．多种修改可组成一个编辑事务

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；本地分类编辑一次删旧关系、改标签、插新关系，任一失败整体撤销。
- **原版现状／替代**：putall本来全批次原子，但只包含插入/更新，无通用transaction；不可把已有回滚称缺失。
- **交付与模块**：增加事务编辑器支持双方向混合写入/删除及显式commit/rollback，保持活跃inverse引用。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_orderedbidict.py`、`bidict/_orderedbase.py`。
- **兼容边界**：单次mutator原有行为保持；事务不承诺跨线程隔离，后续同步适配单列。
- **正常验收**：混合三操作一次生效，失败后原表、inverse与顺序均恢复。
- **异常／边界验收**：嵌套事务、显式rollback、回调异常、旧views、事务关闭后误用。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 03．支持带前置值条件的关系更新

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_bidict.py)；界面修改标签前先确认仍是用户看到的旧关系。
- **原版现状／替代**：无compare_and_set，调用方需自行读后写，无法统一冲突结果。
- **交付与模块**：新增compare_and_set/compare_and_delete，返回成功或结构化当前关系。；`bidict/_bidict.py`、`bidict/_base.py`。
- **兼容边界**：缺失和显式None用专门哨兵区分；线程原子性必须由同步包装保证，普通类只保证单调用前置条件。
- **正常验收**：预期tea时替换成功；预期已过期时不改正反映射。
- **异常／边界验收**：目标值被他键占用、同值no-op、inverse调用对称、自定义相等与hash异常。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 04．冲突处理可由业务resolver决定

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_dup.py)；导入标签时按记录优先级决定保留旧关系或生成新的唯一标签。
- **原版现状／替代**：OnDup只有RAISE/DROP_OLD/DROP_NEW，无法调用一次业务冲突resolver。
- **交付与模块**：增加显式resolver协议，收到新旧关系和冲突类型，返回有限动作或替代关系后再校验。；`bidict/_dup.py`、`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_exc.py`。
- **兼容边界**：现有OnDup枚举默认保持；resolver不是直接修改底层dict的逃生口；回调重入策略明确。
- **正常验收**：只对冲突调用resolver，替代标签唯一后双向一致。
- **异常／边界验收**：键值同时冲突、resolver异常/返回非法类型、新关系仍冲突与原子批次。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 05．批量导入预览完整诊断与行号

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；CSV映射维护者希望一次看到所有冲突行再决定导入。
- **原版现状／替代**：原生putall只抛第一处DuplicationError，错误args没有输入行号或完整批次诊断入口。
- **交付与模块**：新增validate_items/preview_update报告每行接受/忽略/替换及冲突关联行，保持模型不变。；`bidict/_base.py`、`bidict/_exc.py`、`bidict/_dup.py`。
- **兼容边界**：明确定义单次迭代物化成本和最大记录数；诊断不是最终提交，提交仍重验。
- **正常验收**：三行含两种冲突均有准确行号与旧关系，预览前后表不变。
- **异常／边界验收**：输入内部重复、无效pair、不可hash、生成器中途异常及OnDup变化。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 06．双向映射可以按公共中间域组合

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；SKU到标签、标签到本地分类编号可以合成SKU到分类编号。
- **原版现状／替代**：无compose，可字典推导再构造，但缺失中间项需手动定义。
- **交付与模块**：新增compose(other,missing=...)返回双向映射，支持严格或交集域策略。；`bidict/_base.py`、`bidict/_abc.py`。
- **兼容边界**：两个输入需满足一一关系；输出类型和有序策略明确，不偷偷生成多值映射。
- **正常验收**：A->B与B->C组成A->C，inverse等于反向组合。
- **异常／边界验收**：中间域缺项、空表、不同子类、相同输入、自定义映射比较语义。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 07．选择子映射保持双向类型与顺序

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；按选中的SKU或标签导出一个仍能反查的映射。
- **原版现状／替代**：没有select/filter接口，可用items推导手工构造。
- **交付与模块**：统一select(keys/values/predicate)及映射关系交/差选择，保留原类型与有序相对顺序。；`bidict/_base.py`、`bidict/_frozen.py`、`bidict/_orderedbase.py`。
- **兼容边界**：不是把keys视图集合运算包装为新集合类型；不共享可变backing导致副本随原表变。
- **正常验收**：按标签选择后能反查，inverse选择与正向选择结果对应。
- **异常／边界验收**：缺失选择项策略、None、空选择、predicate异常、frozen结果和custom subclass。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 08．键和值转换后生成受校验的新映射

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；把数字SKU转为标准字符串，同时把标签做明确业务规范化。
- **原版现状／替代**：无map_items；可推导构造但类型、碰撞、顺序需每处手工处理。
- **交付与模块**：新增transform_items(key_fn,value_fn)返回新映射并记录转换冲突来源。；`bidict/_base.py`、`bidict/_dup.py`、`bidict/_frozen.py`。
- **兼容边界**：与第1项在既有键集合中重分配不同，此处输出键/值类型可变化且默认不改原表。
- **正常验收**：两侧转换后得到预期类型，inverse转换对称，原表保持。
- **异常／边界验收**：转换把两键/两值合并时拒绝或显式resolver，回调异常、identity保留和frozen子类。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 09．关系差异可生成带前置条件的补丁

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；离线编辑两份标签表后查看改动并应用到基础版本。
- **原版现状／替代**：无diff/apply_patch，需应用自己比dict；现有union并非冲突检测补丁。
- **交付与模块**：新增add/remove/reassign补丁，保存旧关系和有序位置，可逆且按前置条件原子应用。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_orderedbidict.py`。
- **兼容边界**：不按字符串执行操作；同时环形换值使用最终状态验证，不等同顺序putall。
- **正常验收**：diff(a,b)应用于a得到b，逆补丁恢复a与顺序。
- **异常／边界验收**：目标已改、缺失关系、相等对象、重复操作、部分失败和inverse补丁方向。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 10．提供保持活跃关联的只读双向代理

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；向只读展示组件共享实时标签表，但不授予写入入口。
- **原版现状／替代**：frozenbidict是已有独立不可变快照，MappingProxyType只代理一个方向；没有成对readonly view。
- **交付与模块**：提供ReadOnlyBidictProxy，inverse同样只读且inverse.inverse返回同一代理。；`bidict/_base.py`、`bidict/_abc.py`。
- **兼容边界**：不宣称深冻结键值对象；不把现有frozen快照重新计作新能力。
- **正常验收**：源表新增后代理立即可见，两个方向所有修改方法拒绝。
- **异常／边界验收**：源表clear、循环inverse身份、views.mapping不泄露可写底层、copy与线程说明。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 11．有序映射支持明确的位置编辑

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_orderedbidict.py)；本地列表把某SKU插到指定行或移动到另一SKU之前。
- **原版现状／替代**：OrderedBidict只有move_to_end/popitem(last)，没有item_at/insert_at/move_before/index。
- **交付与模块**：提供位置访问及相对插入/移动的完整有序编辑API，复用节点链表并定义索引开销。；`bidict/_orderedbidict.py`、`bidict/_orderedbase.py`。
- **兼容边界**：键查找语义保持；不谎称链表随机访问O(1)，inverse展示同一关系顺序。
- **正常验收**：中间插入和move_before后正反items顺序一致，排名可取回。
- **异常／边界验收**：负索引、边界、移动自身、缺锚点、重复冲突、旧迭代器失效与回滚。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 12．有序映射可以整体稳定重排

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_orderedbidict.py)；界面按标签字母或SKU排序一次，并保持两方向共用顺序。
- **原版现状／替代**：move_to_end可逐项模拟，无reorder/sort；SortedBidict配方已有按backing自动排序的不同能力。
- **交付与模块**：新增reorder完整排列及sort_items(key,reverse)，先验证排列/排序再原子重链。；`bidict/_orderedbidict.py`、`bidict/_orderedbase.py`。
- **兼容边界**：不重新实现已有SortedBidict配方；这是有序关系当前整体顺序的显式操作。
- **正常验收**：完整排列与稳定排序正确，inverse同序，键值关系未改变。
- **异常／边界验收**：漏项/重复项、key异常、全同key、空表和迭代器版本。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 13．修改完成后发布成组变更记录

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；本地界面需要知道标签表实际新增、替换或移除了什么。
- **原版现状／替代**：无observe/change journal，子类可重写_write但要自行合并inverse与rollback事件。
- **交付与模块**：新增订阅协议和不可变ChangeSet，仅成功commit后发送一次，包含关系和顺序变化。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_orderedbidict.py`、`bidict/_orderedbase.py`。
- **兼容边界**：失败或no-op不发布虚假事件；回调异常不能把已提交状态倒退为半状态，明确错误隔离策略。
- **正常验收**：单次和批次写入准确发布，inverse写入也只发布同一关系事件。
- **异常／边界验收**：回调重入、取消订阅、GC引用、rollback、顺序变更与通知失败。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 14．本地编辑提供受限历史的撤销与重做

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；用户误改标签后点击撤销，随后可以重做。
- **原版现状／替代**：没有undo/redo，用户需保存整表copy。
- **交付与模块**：在关系ChangeSet上实现独立History适配器，按事务存历史并限制条数，支持顺序变化。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_orderedbidict.py`。
- **兼容边界**：不启用时零历史开销；仅本地内存，不持久记录任意对象repr。
- **正常验收**：一次混合编辑撤销恢复关系/顺序，重做得到同一结果。
- **异常／边界验收**：撤销后新写清空redo、容量0、超限淘汰、外部旁路变更检测和inverse入口。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；[13]。

## 15．实例可独立配置缺省重复策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；同一进程两份标签表分别严格拒绝覆盖和保留旧值，无需定义两种子类。
- **原版现状／替代**：on_dup是类属性；put可每次传策略，构造关键字会被当普通映射数据。
- **交付与模块**：增加不与数据关键字冲突的工厂/配置入口，使实例策略被copy/union/pickle正确携带。；`bidict/_base.py`、`bidict/_dup.py`、`bidict/_bidict.py`。
- **兼容边界**：现有构造kwargs仍是数据；inverse策略的key/val方向明确，不随意互换全局类变量。
- **正常验收**：两个实例默认策略互不影响，副本与逆向按声明规则使用。
- **异常／边界验收**：OnDup无效值、动态生成inverse class、frozen、data键恰叫on_dup与序列化。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 16．映射提供显式类型codec的记录格式

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；把含tuple键的本地标签表保存为可移植JSON记录，避免JSON对象强制字符串键。
- **原版现状／替代**：有pickle和dict拷贝，无记录codec；JSON直接dump会丢键类型或拒绝tuple键。
- **交付与模块**：新增版本化pairs记录格式，类型codec显式注册、记录有序类型及重复策略。；`bidict/_base.py`、`bidict/_orderedbidict.py`、`bidict/_frozen.py`、`bidict/_iter.py`。
- **兼容边界**：不替换pickle；不从数据执行类名或导入表达式；使用者值编码由显式codec负责。
- **正常验收**：tuple/int/str键值往返后反查/顺序正确，标准JSON解析器可读。
- **异常／边界验收**：未知codec/schema、重复记录、None、保留字碰撞、custom subclass与不可编码对象。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 17．成对正反映射可以共享同步锁

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；多个本地线程维护同一表时，读写两个方向需要统一临界区。
- **原版现状／替代**：普通bidict未提供同步包装；底层dict单操作不等同两索引原子。
- **交付与模块**：新增SynchronizedBidict包装，正反共享RLock，提供明确snapshot迭代及锁内事务。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_orderedbidict.py`、`bidict/_abc.py`。
- **兼容边界**：不改变普通类默认性能；不宣称跨进程共享或分布式锁。
- **正常验收**：两线程合法更新后双向始终一致，inverse与compare_and_set使用同一锁。
- **异常／边界验收**：回调重入、异常释放、跨两个表锁顺序、迭代快照和死锁回归。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 18．有序双向映射可作容量受限的本地LRU

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_orderedbidict.py)；本地格式标签缓存按最近一次正向或反向访问淘汰旧关系。
- **原版现状／替代**：OrderedBidict有顺序节点和popitem，但无capacity或访问淘汰策略。
- **交付与模块**：新增BoundedOrderedBidict适配器，明确访问触发、容量与驱逐ChangeSet。；`bidict/_orderedbidict.py`、`bidict/_orderedbase.py`、`bidict/_bidict.py`。
- **兼容边界**：普通OrderedBidict读取不改顺序；正反访问同一关系，只占一个容量位置。
- **正常验收**：容量2访问a后插c淘汰b，两方向同步移除并报告被淘汰关系。
- **异常／边界验收**：容量0/负数、同值no-op、冲突写入、批量插入淘汰顺序和peek不触发访问。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 19．按显式业务标识索引不可hash记录

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；应用希望保留商品dict对象作为值，但反查以稳定product_id为准。
- **原版现状／替代**：核心要求值可hash，dict值实跑TypeError；可自写mapping子类，但无明确record-key适配类型。
- **交付与模块**：新增KeyedBidict适配器，分开原始对象与canonical key存储，显式inverse_lookup接受标识或对象。；`bidict/_base.py`、`bidict/_bidict.py`、`bidict/_abc.py`。
- **兼容边界**：不改变原生bidict按对象相等/hash的一一语义；原记录标识改变需显式refresh，禁止悄悄跨键。
- **正常验收**：两个不可hash商品记录按ID反查正确，正向仍返回原对象。
- **异常／边界验收**：规范化碰撞、标识缺失、外部改ID、原对象相同不同键、copy与codec。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

## 20．公开检查双向关系与有序节点一致性

- **类型／来源与场景**：enhancement；[来源](https://github.com/jab/bidict/blob/299fedc89f1d70d5d41cf7922564b376d3e2d435/bidict/_base.py)；自定义backing mapping或普通对象生命周期变化后，维护者需要可读诊断。
- **原版现状／替代**：没有public validate/check_invariants，内部一致性主要靠原生测试和用户遵守稳定hash/eq。
- **交付与模块**：新增只读check_invariants报告双向遗漏、长度/对象关联和有序节点问题，提供具体条目但不自动修复。；`bidict/_base.py`、`bidict/_orderedbase.py`、`bidict/_exc.py`。
- **兼容边界**：不把违反hash/eq约定称原生缺陷；诊断不能承诺恢复任意坏对象，也不自动执行修复。
- **正常验收**：合法标准/自定义映射报告通过，构造受控不一致fixture指出精确方向和关系。
- **异常／边界验收**：hash/eq本身抛错、循环节点检测、空表、逆向视图与检查期间变更。
- **原生回归**：`tests/test_bidict.py`。
- **实际依赖／步骤依赖**：Python3.12运行无额外依赖；较早Python需typing_extensions。测试pytest/xdist/Hypothesis/pytest-sphinx及sorted配方依赖；ty严格对齐上游uv.lock 0.0.84，无外部服务。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
