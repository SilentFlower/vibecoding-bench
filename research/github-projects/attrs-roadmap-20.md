# attrs 二十步迭代研究路线

冻结原版：`ee66e7274852438cc23d4240a1a9cd632fda8b52`。本路线为本地研究；20步均未实施，增强提案不代表上游接受。所有正常/异常验收是未来交付目标，当前仅验证原版现状。
原版逐项观察：`/root/project/vibecoding-bench/.deploy/github-100-research/resume-core/attrs/observations-result.json`。步骤01/02/03/05/06是已实证缺陷，其余是明确的新能力提案；第04步的继承语义属于新增可选模式。

## 01．保留数据类自己声明的额外槽位

- **类型与来源／场景**：bug_fix；[官方来源](https://github.com/python-attrs/attrs/issues/1637)；业务类用一个非字段的private槽位缓存计算结果。
- **原版现状**：OwnSlots.private赋值实测TypeError；_create_slots_class只收集基类slots并替换本类slots。
- **交付与真实模块**：合并本类额外槽位与生成字段槽位，移除旧类descriptor并重新建立新类槽位。；`src/attr/_make.py`。
- **兼容边界**：不重复继承槽位；__dict__/__weakref__规则维持；不把额外槽位变成attrs字段。
- **正常验收**：OwnSlots().private=1后可读取1且public保持foo。
- **异常／边界验收**：字段同名槽位、str/dict形式slots、继承冲突、弱引用、pickle和空槽位。
- **原生回归**：`tests/test_slots.py`、`tests/test_make.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 02．astuple递归处理集合中的集合

- **类型与来源／场景**：bug_fix；[官方来源](https://github.com/python-attrs/attrs/issues/1647)；把订单树转为可存储的元组，订单位于list中的list。
- **原版现状**：astuple(Envelope([[Item(...)] ]))实测仍含Item，源码只递归直接元素。
- **交付与真实模块**：为astuple建立贯穿list/tuple/set/dict的递归转换，统一传播filter/tuple_factory。；`src/attr/_funcs.py`。
- **兼容边界**：保持retain_collection_types；dict键转换保持可哈希；非attrs任意对象原样返回。
- **正常验收**：两层list中的Item转为(name,quantity)，结果没有遗留attrs实例。
- **异常／边界验收**：嵌套字典键值、namedtuple、空集合和不可哈希转换错误；循环输入明确报错或沿用既有行为。
- **原生回归**：`tests/test_funcs.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 03．Attribute过滤器按字段身份选择

- **类型与来源／场景**：bug_fix；[官方来源](https://github.com/python-attrs/attrs/issues/1624)；导出一个模型的字段时同名同类型的其他模型字段不应被意外选中。
- **原版现状**：OnlyNameA.x与OnlyNameB.x内容相等，include(A.x)实测导出了B(5).x。
- **交付与真实模块**：在include/exclude的Attribute参数分支按对象身份匹配；类型及字符串名称分支保持。；`src/attr/filters.py`、`src/attr/_make.py`。
- **兼容边界**：字符串x仍跨类匹配；继承共享同一个Attribute的行为明确；不改Attribute的全局相等契约。
- **正常验收**：include(A.x)只允许实际A.x；exclude同样只排除指定字段。
- **异常／边界验收**：相同元数据不同类、字段evolve副本、继承字段、泛型字段以及混合type/name/Attribute参数。
- **原生回归**：`tests/test_filters.py`、`tests/test_funcs.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 04．默认值方法支持显式的继承动态派发

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1549)；子类重写父类字段的默认值方法以切换业务默认。
- **原版现状**：ChildDefault重写_foo_default但foo实测仍为A；Factory存储原函数而不按实例查找。
- **交付与真实模块**：增加明确的动态方法默认值声明或opt-in继承派发模式，调用实例当前绑定方法。；`src/attr/_make.py`。
- **兼容边界**：这是新增契约，保留直接传callable及现有Factory绑定语义；私有方法改名与缺失时报清楚错误。
- **正常验收**：启用动态声明后ChildDefault得到B，BaseDefault仍得到A。
- **异常／边界验收**：多层继承、方法删除、staticmethod/classmethod拒绝边界、工厂抛错及takes_self。
- **原生回归**：`tests/test_make.py`、`tests/test_next_gen.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 05．槽位类pickle保留继承的实例字典

- **类型与来源／场景**：bug_fix；[官方来源](https://github.com/python-attrs/attrs/issues/1643)；普通基类提供__dict__，attrs子类同时含字段槽位与运行备注。
- **原版现状**：SlottedChild(1).memo=retained，pickle往返后__dict__实测为空。
- **交付与真实模块**：生成state同时保存拥有的槽位字段和真实实例字典，反序列化恢复两部分并清空hash缓存。；`src/attr/_make.py`。
- **兼容边界**：读取既有dict/旧tuple状态兼容；不触碰用户自定义getstate/setstate；不序列化弱引用。
- **正常验收**：往返x=1和memo=retained均保留。
- **异常／边界验收**：空dict、字段与dict同名、frozen、cache_hash、多个基类槽位、不同pickle协议。
- **原生回归**：`tests/test_slots.py`、`tests/test_make.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 06．optional转换器兼容字符串类型注解

- **类型与来源／场景**：bug_fix；[官方来源](https://github.com/python-attrs/attrs/issues/1629)；应用启用延迟注解，数字转换器参数和返回注解是字符串。
- **原版现状**：optional(convert)实测在str | None处TypeError，包装器尚未被调用。
- **交付与真实模块**：为参数及返回字符串注解构造兼容的可选类型表示，或在正确globals/locals中解析后组合。；`src/attr/converters.py`、`src/attr/_compat.py`、`src/attr/_make.py`。
- **兼容边界**：不擅自求值未知名称；保留Converter takes_self/takes_field；无注解转换器不新增限制。
- **正常验收**：字符串str到int转换器包装成功，2转2，None仍None。
- **异常／边界验收**：未知前向类型、带引号字符串、Union/Annotated、内置callable、无签名函数。
- **原生回归**：`tests/test_converters.py`、`tests/test_annotations.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 07．深层验证错误带索引和映射键路径

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1245)；列表第二个名称为空时，表单需要标出names[1]而不是整个names。
- **原版现状**：实测错误只显示Length of names，_DeepIterable/_DeepMapping没有记录成员位置。
- **交付与真实模块**：以结构化路径附加到深层异常或提供path-aware包装器，保留原始异常cause。；`src/attr/validators.py`。
- **兼容边界**：不默认重写用户异常类型；映射键repr需安全且有长度边界；现有三参数validator继续可用。
- **正常验收**：names[1]的长度错误明确定位第二项，嵌套映射形成连续路径。
- **异常／边界验收**：同时键/值错误、生成器单次消费、用户自定义异常、深层Optional/or_分支。
- **原生回归**：`tests/test_validators.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 08．字段赋值后触发变化通知

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1437)；响应式模型修改a后监听器需要在实例上读到新a，随后重算b。
- **原版现状**：只有赋值前on_setattr；其返回值仍参与转换，不能安全当作赋值完成通知。
- **交付与真实模块**：新增独立赋值后通知机制，传递实例/字段/旧值/新值，明确相等值和初始化策略。；`src/attr/_make.py`、`src/attr/setters.py`、`src/attr/_next_gen.py`。
- **兼容边界**：保持现有convert/validate先执行；验证失败不通知；通知抛错的值保留语义需显式。
- **正常验收**：监听a变更时self.a已为新值并可正确重算b。
- **异常／边界验收**：递归写同字段检测、互相监听、冻结类拒绝、首次初始化和通知异常。
- **原生回归**：`tests/test_setattr.py`、`tests/test_hooks.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 09．复用生成的字段比较逻辑

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1452)；手写__eq__需要先处理特殊哨兵，再使用自动生成的所有字段比较。
- **原版现状**：实例不存在__attrs_eq__；_make_eq_script直接生成带精确类型检查的__eq__。可保存原__eq__或手工比较，尚无稳定的生成比较辅助协议。
- **交付与真实模块**：提供独立生成比较辅助方法，可由自定义eq显式调用并选择字段比较策略。；`src/attr/_make.py`。
- **兼容边界**：默认__eq__和哈希不改；跨类相等需调用者显式承担对称性/传递性，不自动开放。
- **正常验收**：自定义eq处理哨兵后调用辅助方法，对普通同类对象逐字段返回正确结果。
- **异常／边界验收**：不同类/缺字段返回NotImplemented或明确错误；eq=False字段、eq callable与NaN。
- **原生回归**：`tests/test_dunders.py`、`tests/test_cmp.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 10．把实例演化为兼容目标数据类

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1088)；将基础订单升级为带配送字段的订单子类并保留原字段。
- **原版现状**：evolve只调用inst.__class__(**changes)，不能传目标类型；手写映射会丢alias规则。
- **交付与真实模块**：新增独立演化到目标类的API，按原字段名/目标alias映射公共字段并检查必需字段。；`src/attr/_make.py`。
- **兼容边界**：普通evolve保持；新增字段必须由值/工厂补足；不复制init=False隐藏状态。
- **正常验收**：BaseOrder到ShippedOrder保留公共字段并注入tracking，新实例类型正确。
- **异常／边界验收**：不相关目标、字段别名冲突、目标缺必需值、frozen与目标validator抛错。
- **原生回归**：`tests/test_funcs.py`、`tests/test_make.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 11．演化时选择已规范字段的再转换策略

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1126)；已有字段转换器是有损或昂贵的，修改另一个字段不应被迫再次转换全部字段。
- **原版现状**：evolve构造cls(**changes)，未改字段仍经过converter/validator；这属现有语义。
- **交付与真实模块**：提供显式的新演化模式：未改且已规范字段跳过converter，全部实例约束仍按约定验证。；`src/attr/_make.py`。
- **兼容边界**：默认evolve保持重建；不能把不再验证当性能优化；post_init和init=False状态有明确重建规则。
- **正常验收**：对乘2转换器的原字段，修改无关字段后原值保持而变更字段仍正常转换。
- **异常／边界验收**：跨字段validator、factory、非幂等post_init、可变共享值和输入alias；不通过私有绕写冻结实例。
- **原生回归**：`tests/test_funcs.py`、`tests/test_hooks.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 12．repr字段格式器可访问实例上下文

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1193)；金额repr需要读取同一实例的currency字段，而非只接收数值。
- **原版现状**：field repr callable当前只接收字段值，不能表达实例局部格式规则。
- **交付与真实模块**：增加明确包装器使repr函数可声明接收instance/Attribute/value；默认单值形式保持。；`src/attr/_make.py`。
- **兼容边界**：新增包装器与Converter概念区分；递归repr保护保持，不默认增加字段可见性。
- **正常验收**：相同amount在USD/EUR实例生成对应货币文本。
- **异常／边界验收**：缺字段的初始化中repr、函数抛错、循环引用、repr=False和自定义__repr__。
- **原生回归**：`tests/test_dunders.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 13．根据参数化类型生成深层验证器

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1235)；声明list[str]或dict[str,int]时希望按类型递归验证，不手工嵌套deep_mapping。
- **原版现状**：instance_of(list[str])调用实测TypeError；该函数目前只接受isinstance合法类型。
- **交付与真实模块**：新增独立from_type式构建器，支持明确集合/Union/Optional/Literal，复用deep validators。；`src/attr/validators.py`。
- **兼容边界**：保留instance_of语义；不执行任意注解文本；不把转换混进验证。
- **正常验收**：list[str]拒绝含整数项，dict[str,int]定位错误值，Optional允许None。
- **异常／边界验收**：递归类型、TypeVar未绑定、空容器、tuple长度、bool/int关系与不可支持类型明确错误。
- **原生回归**：`tests/test_validators.py`、`tests/test_annotations.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：[7]。

## 14．显式收集多字段验证报告

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1421)；编辑表单一次返回所有独立字段问题，避免每改一个字段再提交。
- **原版现状**：validate(inst)首个validator抛错即终止，当前签名只含inst。
- **交付与真实模块**：新增report模式或独立validate_all入口，按字段和组合验证器收集结构化错误再返回/抛组。；`src/attr/validators.py`、`src/attr/_make.py`、`src/attr/exceptions.py`。
- **兼容边界**：默认fail-fast保持；不吞BaseException；任意用户validator外部副作用不承诺回滚。
- **正常验收**：两个独立坏字段一次报告两个错误，原实例字段不变。
- **异常／边界验收**：and_/or_/optional组合、同字段多个错、异常嵌套、无错空报告以及禁用配置。
- **原生回归**：`tests/test_validators.py`、`tests/test_make.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：[7]。

## 15．验证开关支持任务局部作用域

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/blob/ee66e7274852438cc23d4240a1a9cd632fda8b52/src/attr/_config.py)；异步数据导入临时禁用自身验证时，同进程表单请求仍需正常验证。
- **原版现状**：validators.disabled通过_config的进程级变量开关；文档明确非线程安全。
- **交付与真实模块**：新增ContextVar支持的局部禁用上下文，生成代码统一调用有效开关查询。；`src/attr/_config.py`、`src/attr/validators.py`、`src/attr/_make.py`。
- **兼容边界**：保留全局set_disabled显式语义；局部优先级、嵌套恢复及任务继承规则明确。
- **正常验收**：两个asyncio任务交错运行时，一个临时禁用不影响另一个拒绝坏值。
- **异常／边界验收**：异常退出嵌套、线程、copy_context、全局开关改变和生成init/setattr/validate路径一致。
- **原生回归**：`tests/test_config.py`、`tests/test_validators.py`、`tests/test_setattr.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 16．公开查看生成方法的源代码

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1472)；排查字段转换顺序时希望一次查看生成的init/eq/repr，而非挖linecache。
- **原版现状**：attrs.inspect返回ClassProps，不返回生成源码；inspect.getsource(Item.__init__)已能逐方法查看，内部代码已通过linecache保存。新增目标是集中枚举实际生成方法及来源，不重复宣称逐方法取源码缺失。
- **交付与真实模块**：提供只读源码检查API，按方法名导出实际生成代码及可用的来源信息。；`src/attr/_make.py`、`src/attr/_next_gen.py`。
- **兼容边界**：不把Python对象repr当可执行完整类定义；用户自定义方法标明未生成；不暴露任意闭包值。
- **正常验收**：对Item查看init可见int转换及数量验证，eq/repr与当前方法对应。
- **异常／边界验收**：自定义init、slots替换、linecache失效、继承方法、函数被猴补后的来源状态。
- **原生回归**：`tests/test_make.py`、`tests/test_next_gen.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 17．公开槽位缓存属性的原始函数元信息

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1532)；文档生成器需要读取cached_property的签名和文档，槽位转换后descriptor已被替换。
- **原版现状**：生成器只在内部cached_properties字典保存函数，公开inspect无该映射。
- **交付与真实模块**：通过只读检查结构暴露cached_property原函数、声明类及缓存槽名。；`src/attr/_make.py`、`src/attr/_next_gen.py`。
- **兼容边界**：不暴露可修改的生成器内部dict；继承/override应返回最终获胜定义。
- **正常验收**：槽位类缓存属性的原函数签名与doc可读取，访问仍仅计算一次。
- **异常／边界验收**：子类覆盖同名属性、普通property、非槽位类、动态删除及自定义__getattr__。
- **原生回归**：`tests/test_slots.py`、`tests/test_next_gen.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 18．字段文档保留到槽位descriptor

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1294)；交互帮助需要展示字段单位与含义，代码使用slots节省内存。
- **原版现状**：field没有doc参数，生成__slots__为tuple，descriptor无字段业务文档。
- **交付与真实模块**：增加字段文档元信息并在支持解释器上生成slots文档映射，同时暴露检查入口。；`src/attr/_make.py`、`src/attr/_next_gen.py`。
- **兼容边界**：不从任意metadata键猜文档；已有metadata不变；继承槽位不重复创建。
- **正常验收**：inspect.getdoc(Sensor.temperature)显示明确单位，实例布局和赋值不变。
- **异常／边界验收**：空文档、Unicode、多层继承、复用槽位、frozen、非slots类和make_class。
- **原生回归**：`tests/test_slots.py`、`tests/test_make.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 19．稳定的第三方字段声明扩展协议

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1543)；库作者在field之上增加业务装饰器，不希望依赖私有_CountingAttr计数和具体类型。
- **原版现状**：_transform_attrs识别特定_CountingAttr声明；没有公开可注册的声明转换协议。
- **交付与真实模块**：提供受限公开字段声明适配协议，把扩展对象转换为标准Attribute/field声明，保持顺序。；`src/attr/_make.py`、`src/attr/_next_gen.py`。
- **兼容边界**：现有field语义和排序不变；不接收任意对象为字段，避免普通默认值被误识别。
- **正常验收**：注册的业务字段可带自定义validator装饰器并按源码顺序生成字段。
- **异常／边界验收**：无效适配器、重复名字、继承、field_transformer顺序、适配异常与普通对象默认值。
- **原生回归**：`tests/test_make.py`、`tests/test_annotations.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。

## 20．显式传递每次验证的业务上下文

- **类型与来源／场景**：enhancement；[官方来源](https://github.com/python-attrs/attrs/issues/1421)；同一模型在宽松草稿与严格提交模式使用不同业务验证，不创建多个全局validator。
- **原版现状**：validate仅接受inst；三参数validator无法得到本次locale/strict上下文。
- **交付与真实模块**：独立的上下文validator包装器与validate context参数，将上下文显式传给声明接收它的函数。；`src/attr/validators.py`、`src/attr/_make.py`。
- **兼容边界**：与第14步错误收集独立；不依赖全局变量；老三参数validator不接收额外kwargs。
- **正常验收**：同实例草稿模式允许缺省值，strict上下文要求完整；旧validator照常工作。
- **异常／边界验收**：嵌套深层验证上下文、并发请求隔离、不可变上下文、未知参数以及生成init没有上下文的默认行为。
- **原生回归**：`tests/test_validators.py`、`tests/test_make.py`。
- **实际依赖**：Python标准库；沿用冻结pytest/hypothesis测试依赖，无额外运行包。；步骤依赖：无。
