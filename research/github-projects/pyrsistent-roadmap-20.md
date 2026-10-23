# Pyrsistent 二十步迭代研究路线

固定[tobgu/pyrsistent@0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7](https://github.com/tobgu/pyrsistent/tree/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已存在get_in、PMap.__or__、pmap的pairs构造、两参transform匹配器、字段/全局不变量、PRecord/PClass多字段set和多重集运算，不重复计作新能力。

## 01．嵌套CheckedPMap传递ignore_extra策略

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_checked_types.py)；导入上游表单多出的展示字段时，嵌套记录仍应遵循调用者ignore_extra。
- **原版现状／替代**：Items.create(ignore_extra=True)遇到值中的label仍AttributeError；CheckedPMap递归create没转发参数，optional pmap_field工厂也无该参数。
- **交付与模块**：在映射键值递归构造和可选字段工厂完整传递已声明策略。；`pyrsistent/_checked_types.py`、`pyrsistent/_field_common.py`。
- **兼容边界**：默认False仍拒绝额外字段；已是目标类型的实例保持复用；非checked普通工厂不强加参数。
- **正常验收**：含额外label的嵌套Item按True成功，按False失败。
- **异常／边界验收**：多层map/vector/record组合、None可选值、键类型与已有对象；不吞非额外字段错误。
- **原生回归**：`tests/checked_map_test.py`、`tests/field_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 02．自动序列字段缓存隔离item_invariant

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_field_common.py)；不同表单都声明int向量，但分别约束正数和负数。
- **原版现状／替代**：第二个负数类复用第一个正数类的IntPVector；缓存键只有checked_class/item_type，忽略item_invariant。
- **交付与模块**：把不变量身份纳入生成类型和pickle恢复标识，避免跨类约束串用。；`pyrsistent/_field_common.py`。
- **兼容边界**：不改变同一字段已有约束；pickle旧数据需明确兼容方案，不能复用错误类只求可解码。
- **正常验收**：两个声明顺序互换后各自接受自己的数，拒绝另一类。
- **异常／边界验收**：同type不同闭包、相同函数复用、pset_field、模块重载和pickle往返。
- **原生回归**：`tests/field_test.py`、`tests/checked_vector_test.py`、`tests/checked_set_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 03．PDeque切片遵循序列边界归一化

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pdeque.py)；分页取队列前len条应得到全队列，超界起点应为空。
- **原版现状／替代**：[1,2,3][:3]实跑为空，[3:]仍全量，[20:]为[3]，空队列[1:]ZeroDivisionError；当前用模长度。
- **交付与模块**：用slice.indices统一切片边界，保留双列表共享和maxlen属性。；`pyrsistent/_pdeque.py`。
- **兼容边界**：step!=1现有tuple回退保留；不改变pop负count的另一端语义。
- **正常验收**：与list的同一切片逐项等值，包括[:len]和[len:]。
- **异常／边界验收**：空队列、极大正负边界、逆序、step0应ValueError、maxlen及原对象不变。
- **原生回归**：`tests/deque_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 04．零容量PDeque始终不保留元素

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pdeque.py)；禁用历史记录时业务把maxlen设为0。
- **原版现状／替代**：pdeque([1,2],maxlen=0)保留两项，源于t[-0:]；标准deque为空。
- **交付与模块**：构造和append/extend两端统一处理容量0，保持长度约束。；`pyrsistent/_pdeque.py`。
- **兼容边界**：已有负maxlen检查保留；不把负容量列为新能力，正容量截断规则保持。
- **正常验收**：容量0构造和任意两端添加后长度始终0；正容量仍保留正确端。
- **异常／边界验收**：空生成器、maxlen非整数、负数原有异常、切片和pickle继承容量。
- **原生回归**：`tests/deque_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 05．CheckedPMap序列化向嵌套值传递format

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_checked_types.py)；同一记录独立序列化和放入map后都要使用json字段策略。
- **原版现状／替代**：直接serialize(json)得到json:2，嵌套map得到None:2；默认serializer对子值调用serialize()遗漏format。
- **交付与模块**：默认键值serializer递归传入调用format，审查checked序列同一路径。；`pyrsistent/_checked_types.py`。
- **兼容边界**：显式自定义__serializer__仍拥有结果；format=None默认输出不变。
- **正常验收**：同对象直接与嵌套map序列化format一致。
- **异常／边界验收**：嵌套键、集合/向量、None和未知format、自定义serializer及多层组合。
- **原生回归**：`tests/checked_map_test.py`、`tests/checked_vector_test.py`、`tests/checked_set_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 06．提供仅在最终状态验证的原子多路径变换

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_transformations.py)；low<=high区间从1/2同时改为3/4，中间状态无业务意义。
- **原版现状／替代**：连续transform每路径生成persistent并立刻校验，low=3先失败；set多字段或手动evolver可部分替代。
- **交付与模块**：新增显式atomic变换事务，合并路径写入后仅校验最终不可变对象。；`pyrsistent/_transformations.py`、`pyrsistent/_pclass.py`、`pyrsistent/_precord.py`。
- **兼容边界**：默认逐路径校验保持；嵌套CheckedType必须明确提交边界，不允许最终非法对象。
- **正常验收**：区间两路径更新成功且原对象不变，最终3/2则失败。
- **异常／边界验收**：路径重叠、删除必填、多个层级、命令异常回滚和factory只对改变字段运行。
- **原生回归**：`tests/transform_test.py`、`tests/class_test.py`、`tests/record_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 07．PMap批量更新接收键值对迭代器

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pmap.py)；CSV读取器逐行给出(key,value)，不想先生成dict。
- **原版现状／替代**：pmap构造已接收pairs；update/update_with仍逐输入调用.items()，实跑list pairs AttributeError。
- **交付与模块**：统一mapping或single-pass pairs输入适配，保留update_with冲突合并。；`pyrsistent/_pmap.py`。
- **兼容边界**：已有多mapping按从左到右覆盖；不重复实现已存在构造能力。
- **正常验收**：list/生成器pairs和mapping给出同结果，重复键顺序与dict.update契约明确。
- **异常／边界验收**：错长tuple、迭代中异常、空输入、CheckedPMap约束及冲突函数抛错。
- **原生回归**：`tests/map_test.py`、`tests/checked_map_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 08．不可变向量支持区间splice插入替换

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pvector.py)；在不可变编辑模型中一次插入多行或替换一个选区。
- **原版现状／替代**：PVector只有append/extend/set/mset/delete，没有insert/splice；应用可切片拼接。
- **交付与模块**：新增splice(start,delete_count,items)并在Python/C实现和evolver保持相同语义。；`pyrsistent/_pvector.py`、`pvectorcmodule.c`。
- **兼容边界**：明确负索引/越界夹取与单次消费；不改变set(len)追加行为。
- **正常验收**：中间一次插入多行和区间替换正确，原向量不变。
- **异常／边界验收**：32/1024树节点边界、空替换、同一向量来源、负delete_count及Python/C一致。
- **原生回归**：`tests/vector_test.py`、`tests/hypothesis_vector_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 09．变换可以选择缺失路径处理策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_transformations.py)；批量升级配置时需要区分缺失则忽略、报错或自动建map。
- **原版现状／替代**：现有transform默认自动创建pmap；discard缺失已会跳过，没有显式统一策略。
- **交付与模块**：新增missing=create/skip/error选项及准确缺失路径错误。；`pyrsistent/_transformations.py`。
- **兼容边界**：当前create默认保持；不把已有discard跳过称新增；序列补位不得悄悄填None。
- **正常验收**：同一缺失路径在三种策略下分别创建/原样/报错。
- **异常／边界验收**：中间标量、None、越界索引、匹配器无匹配及删除命令。
- **原生回归**：`tests/transform_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 10．公开稳定的记录字段描述API

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_field_common.py)；表单生成器需要读取类型、必填、初值和serializer。
- **原版现状／替代**：仅有_pclass_fields/_precord_fields私有dict，公开fields入口不存在。
- **交付与模块**：提供只读字段描述对象和fields(cls)函数，含继承后的字段定义与声明来源。；`pyrsistent/_field_common.py`、`pyrsistent/_pclass.py`、`pyrsistent/_precord.py`、`pyrsistent/__init__.py`。
- **兼容边界**：返回快照或只读视图，不允许外部修改真实校验定义；不求执行callable initial。
- **正常验收**：PClass/PRecord包含全部继承字段及覆盖信息，顺序定义清楚。
- **异常／边界验收**：非记录类型、同名覆盖、多继承、前向类型字符串和未设置初值。
- **原生回归**：`tests/field_test.py`、`tests/class_test.py`、`tests/record_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 11．可选从类型注解声明记录字段

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_field_common.py)；新业务模型希望写quantity:int同时保留持久化语义。
- **原版现状／替代**：只声明__annotations__不会生成field，构造quantity时AttributeError；显式field仍可用。
- **交付与模块**：增加opt-in注解声明装饰器，支持限定的基础类型/Optional/容器并转为原生字段。；`pyrsistent/_field_common.py`、`pyrsistent/_pclass.py`、`pyrsistent/_precord.py`。
- **兼容边界**：显式field优先；未知typing构造明确拒绝，不将typing对象直接传isinstance。
- **正常验收**：启用后注解int自动检查，既有显式字段行为不变。
- **异常／边界验收**：Union/Optional、ForwardRef、ClassVar、继承覆盖、默认值和不支持类型。
- **原生回归**：`tests/typing_test.py`、`tests/field_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 12．标准dataclass与持久记录的显式适配

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_helpers.py)；应用边界已有dataclass对象，需要转换为快照再返回原模型。
- **原版现状／替代**：没有dataclass导出适配器，可用asdict再手工create，且类型/默认信息容易重复。
- **交付与模块**：新增from_dataclass/to_dataclass及显式类映射，保留嵌套容器和字段别名策略。；`pyrsistent/_helpers.py`、`pyrsistent/_field_common.py`、`pyrsistent/_pclass.py`、`pyrsistent/_precord.py`。
- **兼容边界**：只处理声明模型，不把任意对象__dict__当字段；不依赖注解字段生成功能。
- **正常验收**：嵌套dataclass转持久对象再回原类值相等、原可变输入不被修改。
- **异常／边界验收**：init=False、kw_only、冻结/slots、缺字段、字段名冲突及用户factory异常。
- **原生回归**：`tests/freeze_test.py`、`tests/class_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 13．嵌套构造错误提供完整业务路径

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_checked_types.py)；批量商品导入需要定位items/tea/quantity而非只有Item.quantity。
- **原版现状／替代**：PTypeError有source_class/field但嵌套create丢失外层key；实跑错误只含Item.quantity。
- **交付与模块**：新增结构化ValidationIssue路径与可选收集模式，同时覆盖类型/字段/全局不变量。；`pyrsistent/_checked_types.py`、`pyrsistent/_field_common.py`、`pyrsistent/_pclass.py`、`pyrsistent/_precord.py`。
- **兼容边界**：默认原异常类型保持或作兼容子类；不执行失败后未明确允许的有副作用factory。
- **正常验收**：错误报告包含完整键/索引路径、错误码及实际类型。
- **异常／边界验收**：多处失败收集、缺字段、不可序列化键、全局错误路径及首错模式。
- **原生回归**：`tests/checked_map_test.py`、`tests/record_test.py`、`tests/class_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 14．序列化可以显式传递业务上下文

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_checked_types.py)；同一价格快照按调用场景选择币种或展示精度，不应使用全局变量。
- **原版现状／替代**：serialize只有format，serializer只能通过闭包或预建不同类获取上下文。
- **交付与模块**：新增可选context并定义serializer协议适配，递归同一请求上下文。；`pyrsistent/_checked_types.py`、`pyrsistent/_field_common.py`、`pyrsistent/_pclass.py`、`pyrsistent/_precord.py`。
- **兼容边界**：format保持原意；旧二参serializer兼容，不靠捕获任意TypeError判签名。
- **正常验收**：相同快照两个context产生不同合法输出，并发不串值。
- **异常／边界验收**：空context、递归checkedmap、自定义serializer协议、异常来源和上下文只读约定。
- **原生回归**：`tests/field_test.py`、`tests/checked_map_test.py`、`tests/class_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 15．freeze和thaw提供局部类型适配器

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_helpers.py)；正常离线模型包含deque和业务值对象，需要显式转换。
- **原版现状／替代**：freeze(deque)原样返回可变deque，支持类型硬编码，无registry参数。
- **交付与模块**：增加每次调用的适配器映射，支持双向转换和递归委托，不设全局可变注册表。；`pyrsistent/_helpers.py`。
- **兼容边界**：默认原支持类型与strict语义保持；自定义对象不默认遍历内部属性。
- **正常验收**：显式deque适配后快照与原队列独立，thaw按声明恢复。
- **异常／边界验收**：子类优先级、递归适配、未注册类型、循环输入明确报错及上下文隔离。
- **原生回归**：`tests/freeze_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 16．提供持久状态的结构化差异和补丁

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_transformations.py)；编辑器撤销/同步本地版本需要两份快照之间的可应用变更。
- **原版现状／替代**：没有diff/patch公开入口，调用方只能自行递归对比并transform。
- **交付与模块**：新增带路径的add/remove/replace差异与apply_patch，定义序列索引和前置值检查。；`pyrsistent/_transformations.py`、`pyrsistent/_pmap.py`、`pyrsistent/_pvector.py`、`pyrsistent/_helpers.py`。
- **兼容边界**：补丁是普通数据，不执行字符串命令；不宣称全局最小编辑距离；与已有transform共存。
- **正常验收**：diff(a,b)应用于a得到b，a保持，逆补丁回到a。
- **异常／边界验收**：相同状态空补丁、删除缺失、列表索引偏移、CheckedType约束和冲突拒绝。
- **原生回归**：`tests/transform_test.py`、`tests/map_test.py`、`tests/vector_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 17．PBag支持计数映射导入与导出

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pbag.py)；汇总订单已是Counter，想保留茶叶数量3而非只遍历一次键。
- **原版现状／替代**：pbag(Counter(tea=3))按迭代器解释为一个tea；目前只有按元素构造和多重集运算。
- **交付与模块**：新增明确from_counts/to_counts以及批量计数更新，校验计数范围。；`pyrsistent/_pbag.py`。
- **兼容边界**：pbag(iterable)原义保持；不把Counter当前迭代语义当缺陷。
- **正常验收**：Counter计数3导入后count为3，导出Counter等值。
- **异常／边界验收**：零/负/非整数计数策略、空计数、超大合法数量不展开副本、相加和差集。
- **原生回归**：`tests/bag_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 18．PDeque增加批量编辑evolver

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pdeque.py)；本地工作队列一次进行两端追加和移除，最后生成一个新快照。
- **原版现状／替代**：PDeque没有evolver，现有每次操作即返回新队列；其他核心容器已有evolver。
- **交付与模块**：新增队列evolver以批量两端操作，persistent后可继续编辑且保持旧快照。；`pyrsistent/_pdeque.py`。
- **兼容边界**：沿用当前pop返回队列语义而非可变deque返回元素；保留maxlen。
- **正常验收**：多次批量操作与逐步不可变操作结果一致；未改动persistent返回原对象。
- **异常／边界验收**：容量0/满容量、负count、提交后再编辑、迭代和多个evolver隔离。
- **原生回归**：`tests/deque_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 19．提供显式冲突策略的递归map合并

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pmap.py)；合并本地配置时保留a.x并补a.y，数组则按业务替换。
- **原版现状／替代**：update/update_with是浅层冲突函数；样例a.x直接被a.y子map覆盖，可自行写递归函数。
- **交付与模块**：提供deep_merge入口，明确mapping递归、sequence替换/拼接和标量冲突resolver。；`pyrsistent/_pmap.py`、`pyrsistent/_transformations.py`。
- **兼容边界**：普通update保持浅合并；不默认拼接列表或强制改变CheckedType。
- **正常验收**：两层配置保留旧键并补新键，用户resolver在冲突完整路径收到值。
- **异常／边界验收**：None与缺失、不同容器类型、类型约束、键冲突、resolver异常和空输入。
- **原生回归**：`tests/map_test.py`、`tests/transform_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

## 20．向量提供保留不可变类型的稳定排序

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobgu/pyrsistent/blob/0c0b7aec8cd25b1d2d8ba07b10acdefd0f38f2c7/pyrsistent/_pvector.py)；展示快照集合按价格和序号排序，希望结果仍可作为同型向量继续编辑。
- **原版现状／替代**：PVector没有sort/sorted入口，可pvector(sorted(v))但CheckedPVector类型和约束需手工重建。
- **交付与模块**：增加返回新向量的sorted(key,reverse)接口，Python/C和checked子类保留合法类型。；`pyrsistent/_pvector.py`、`pyrsistent/_checked_types.py`、`pvectorcmodule.c`。
- **兼容边界**：不原地修改；命名和返回值明确，稳定性沿用Python排序语义。
- **正常验收**：相同key保持原顺序，reverse和key生效，checked类型结果仍正确。
- **异常／边界验收**：空/单项、key异常、不可比较值、Python/C一致及原向量/哈希不变。
- **原生回归**：`tests/vector_test.py`、`tests/checked_vector_test.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；当前安装可选C扩展pvectorc；测试pytest/hypothesis/typing_extensions，标准库dataclasses/collections适配不引入服务。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
