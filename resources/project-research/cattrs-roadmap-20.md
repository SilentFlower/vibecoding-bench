# cattrs 二十步迭代研究路线

固定 [python-attrs/cattrs@57333a234a19903a94e5b181bc0aee6b187ee05c](https://github.com/python-attrs/cattrs/tree/57333a234a19903a94e5b181bc0aee6b187ee05c)。全为研究提案，尚未实施。第01/02步为固定提交已复现缺陷，其余18步为明确增强；来源issue不表示上游承诺。
源码核对已排除现成的Annotated override、默认值经attrs converter规范化、PEP695联合别名、具体Path和整类方法策略。原版观察保存在observations-result.json，正常／异常验收均为未来目标。

## 01．联合判别正确识别dataclass的default_factory

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-attrs/cattrs/issues/796)；订单两种dataclass共享x，其中一种额外含默认空标签；缺标签时不能悄悄变成另一个类型。
- **原版现状／已有替代**：实际structure({x:1},D1|D2)得到D2；disambiguators直接检查原dataclass Field.default，忽略default_factory。
- **交付与影响模块**：按adapted_fields规范后的默认值判定必需字段，对真正歧义抛TypeError。；`src/cattrs/disambiguators.py`、`src/cattrs/_compat.py`。
- **兼容边界**：不凭联合顺序猜类型；已有唯一必需字段、Literal和override重命名保持。
- **正常验收**：带默认工厂的两种类歧义时明确失败，含真实判别字段时返回正确类型。
- **异常／边界验收**：普通默认值、Factory takes_self、空集合、不同union顺序与泛型dataclass。
- **原生回归**：`tests/test_disambiguators.py`、`tests/test_dataclasses.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 02．msgspec递归层保持同一组cattrs钩子

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-attrs/cattrs/issues/795)；递归事件树每层日期使用秒数编码，私有业务字段也应保留。
- **原版现状／已有替代**：已跑Event：顶层at为1767225600，子层at却为ISO字符串；探测guard返回to_builtins并被烘焙进递归处理器。
- **交付与影响模块**：分离探测与正式生成，递归回退使用延迟cattrs分派，合并同源的私有字段丢失症状。；`src/cattrs/preconf/msgspec.py`、`src/cattrs/gen/__init__.py`。
- **兼容边界**：保留对没有自定义钩子的msgspec直接处理优化；不将循环对象图当普通递归类型。
- **正常验收**：同一棵事件树每层at都是自定义整数，互递归A/B每层私有字段完整。
- **异常／边界验收**：自递归/互递归、无子项、dataclass私有字段、后注册hook缓存失效与真正对象循环。
- **原生回归**：`tests/preconf/test_msgspec_cpython.py`、`tests/test_recursive.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 03．JSON和YAML精确金额的Decimal预配置

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/761)；导出金额19.99并读回精确十进制值，避免业务方每次注册两套钩子。
- **原版现状／已有替代**：JSON dumps(Money(Decimal(...)))实跑TypeError；当前预配置没有Decimal。可以显式注册str与Decimal钩子。
- **交付与影响模块**：增加明确的字符串Decimal策略并在json/pyyaml预配置可选择启用。；`src/cattrs/preconf/json.py`、`src/cattrs/preconf/pyyaml.py`。
- **兼容边界**：默认是否启用需发布兼容决策；不转换为float；后注册用户钩子仍优先。
- **正常验收**：金额19.99及高精度长数字以字符串往返且Decimal相等。
- **异常／边界验收**：NaN/Infinity策略、无效数字、负零、指数形式、None及非Decimal同名对象。
- **原生回归**：`tests/test_preconf.py`、`tests/preconf/test_pyyaml.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 04．结构钩子能够委托给下一个匹配规则

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/794)；类方法先将字符串规范成字典，再交回标准结构器，避免重复实现全部类转换。
- **原版现状／已有替代**：get_structure_hook只有type/cache_result；再次请求同类返回自身规则，dispatch只返回首个匹配。可在注册前保存旧hook，但不能动态层叠。
- **交付与影响模块**：提供受限的next/delegate查询句柄，绑定当前规则位置并保持稳定优先级。；`src/cattrs/dispatch.py`、`src/cattrs/converters.py`、`src/cattrs/strategies/_class_methods.py`。
- **兼容边界**：普通get_structure_hook保持；缓存键包含委托位置，不通过修改私有handler列表实现。
- **正常验收**：两个规范化包装器依次执行后进入默认类结构器，字段类型正确。
- **异常／边界验收**：无下一个规则、递归委托、自注册替换、predicate抛错、复制converter与factory重复。
- **原生回归**：`tests/test_factory_hooks.py`、`tests/test_multistrategy_dispatch.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 05．支持完全空白规则的Converter构造

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/793)；项目的子converter应优先继承父converter全部规则，仅覆盖本地特殊字段。
- **原版现状／已有替代**：BaseConverter和Converter构造都会安装默认规则；fallback父hook会被本地默认类规则抢先。
- **交付与影响模块**：新增明确的空规则构造模式或专用构造器，再显式安装需要的默认策略。；`src/cattrs/converters.py`、`src/cattrs/dispatch.py`。
- **兼容边界**：默认构造行为保持；空模式没有暗含primitive/attrs规则，缺处理器时清楚报错。
- **正常验收**：空子converter把普通attrs类型委托给父自定义factory，并允许子显式覆盖。
- **异常／边界验收**：无父规则、双向fallback环、primitive、空容器、copy和注册后缓存失效。
- **原生回归**：`tests/test_baseconverter.py`、`tests/test_factory_hooks.py`、`tests/test_copy.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 06．原生提供单个序列分支的联合策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/743)；字段既可是一条产品记录也可是一组产品记录。
- **原版现状／已有替代**：Sequence[Product]|Product实跑StructureHandlerNotFoundError；用户可写union factory。
- **交付与影响模块**：新增opt-in单序列联合策略，按输入的序列形状选择唯一序列分支或剩余分支。；`src/cattrs/strategies/_unions.py`、`src/cattrs/converters.py`。
- **兼容边界**：不改变普通union默认选择；字符串/bytes不默认视作业务序列；多个序列分支明确歧义。
- **正常验收**：dict输入结构成Product，列表输入结构成Sequence[Product]且数量字段规范化。
- **异常／边界验收**：空序列、tuple、生成器是否接受、嵌套Optional、错误元素和多个非序列分支。
- **原生回归**：`tests/test_unions.py`、`tests/test_structure.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 07．提供可机读的验证错误记录

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/blob/57333a234a19903a94e5b181bc0aee6b187ee05c/src/cattrs/v.py)；前端需要字段路径tokens、目标类型和错误码，无需解析英文提示。
- **原版现状／已有替代**：transform_error实跑仅返回字符串列表；原始ExceptionGroup和ValidationNote已保留信息，可自行遍历但没有统一记录导出。
- **交付与影响模块**：增加独立错误记录转换器，输出path tokens/code/expected_type/message/cause索引，兼容旧字符串格式器。；`src/cattrs/v.py`、`src/cattrs/errors.py`。
- **兼容边界**：不改变现有transform_error返回类型；不序列化整个输入值或异常任意属性。
- **正常验收**：quantity坏值形成字段token quantity和明确转换错误码，嵌套列表保留整数索引。
- **异常／边界验收**：带点和方括号的字典键、多个错误、未带note的用户异常、异常cause与空args。
- **原生回归**：`tests/test_v.py`、`tests/test_errors.py`、`tests/test_validation.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 08．字段钩子显式取得实例与字段上下文

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/746)；同一个金额字段的导出规则要读取实例currency，结构规则要读取声明类常量与字段metadata。
- **原版现状／已有替代**：override.struct_hook仅(value,type)，unstruct_hook仅(value)；已有use_class_methods只作用整个类，可手写完整类hook。
- **交付与影响模块**：增加明确的字段上下文钩子包装器；导出传instance/Attribute/value，结构传声明类/Attribute/原输入与converter。；`src/cattrs/gen/__init__.py`、`src/cattrs/gen/_shared.py`。
- **兼容边界**：不虚构结构阶段完整实例；旧hook不增加参数；不隐式执行任意field方法名。
- **正常验收**：金额字段根据实例货币格式导出，结构钩子根据类声明前缀读入且其他字段仍用默认规则。
- **异常／边界验收**：字段alias、继承、尚未结构的兄弟字段不可用、hook抛错进入字段错误、dataclass。
- **原生回归**：`tests/test_gen_dict.py`、`tests/strategies/test_class_methods.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 09．预配置bytes编码可选base64

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/552)；与常见JSON客户端交换二进制数据，双方用标准base64。
- **原版现状／已有替代**：JSON预配置固定b85encode/b85decode，hello实跑Xk~0{Zv；手工覆盖两套bytes钩子可替代。
- **交付与影响模块**：json/ujson/orjson预配置提供显式bytes编码选择，成对配置编码和解码。；`src/cattrs/preconf/json.py`、`src/cattrs/preconf/ujson.py`、`src/cattrs/preconf/orjson.py`。
- **兼容边界**：默认base85保持；msgspec原有base64不重复新增；不自动猜输入编码。
- **正常验收**：启用base64后hello导出aGVsbG8=并原样读回bytes。
- **异常／边界验收**：空bytes、非ASCII字节、错误padding、非法字符、嵌套bytes与用户覆盖优先级。
- **原生回归**：`tests/test_preconf.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 10．子类可选择继承父类字段覆盖规则

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/538)；FruitBasket的apples始终导出bananas，子类只声明自身oranges到peaches。
- **原版现状／已有替代**：两个独立生成hook实跑输出apples与peaches，父覆盖未自动合并；目前可手工复制overrides。
- **交付与影响模块**：新增按声明类MRO继承覆盖的opt-in策略，子字段覆盖优先并形成可检查的最终映射。；`src/cattrs/gen/__init__.py`、`src/cattrs/converters.py`。
- **兼容边界**：保留现有独立hook行为；不把整个父hook复用于子类而丢新增字段。
- **正常验收**：子类结果同时为bananas和peaches，父实例仍正确。
- **异常／边界验收**：菱形继承冲突、相同导出键、字段移除、structure/unstructure不同覆盖和泛型父类。
- **原生回归**：`tests/test_converter_inheritance.py`、`tests/test_gen_dict.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 11．全Converter可配置包含init=False字段

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/482)；许多数据类包含计算后缓存/展示字段，导出时希望统一包含。
- **原版现状／已有替代**：Derived含cached但实跑只导出x；gen每类有_cattrs_include_init_false，Converter构造无全局配置。
- **交付与影响模块**：增加converter级导出默认开关并传播所有类生成入口，保留每类覆盖。；`src/cattrs/converters.py`、`src/cattrs/gen/__init__.py`。
- **兼容边界**：第一版限定导出；读入init=False继续单独明确opt-in，不绕过frozen或post_init。
- **正常验收**：全局开启后多种attrs/dataclass导出非init字段，每类关闭仍省略。
- **异常／边界验收**：未赋值字段处理、frozen、继承、copy、用户hook与字段显式omit。
- **原生回归**：`tests/test_gen_dict.py`、`tests/test_dataclasses.py`、`tests/test_copy.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 12．严格原始类型结构策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/469)；配置字段声明int时希望拒绝文本2，确保输入格式错误不被自动掩盖。
- **原版现状／已有替代**：Converter.structure("2",int)实跑得到2，默认primitive handler调用类型构造；可手工逐类注册严格hook。
- **交付与影响模块**：提供opt-in严格primitive配置组合，按明确bool/int/float规则检查实际输入而不强制转换。；`src/cattrs/converters.py`、`src/cattrs/strategies/__init__.py`。
- **兼容边界**：保留默认宽松转换；bool不能偶然通过int；接受int作float是否允许需明确选项。
- **正常验收**：严格模式int拒绝字符串、接受真实int，嵌套字段错误有原路径。
- **异常／边界验收**：bool/int、NaN、字符串子类、枚举、NewType、Literal及Optional组合。
- **原生回归**：`tests/test_structure.py`、`tests/test_validation.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 13．导出前可选择按声明类型验证

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/433)；调用方构造出错误类型的产品，写JSON之前希望得到明确字段错误。
- **原版现状／已有替代**：Product(quantity="bad")未配置attrs validator时，unstructure原样导出bad；这是现有非验证型导出契约。
- **交付与影响模块**：新增独立validated-unstructure入口或显式策略，先依据声明类型检查对象再按现有hook导出。；`src/cattrs/converters.py`、`src/cattrs/gen/__init__.py`、`src/cattrs/errors.py`。
- **兼容边界**：保持默认unstructure不做类型验证；不通过structure重建对象触发构造副作用。
- **正常验收**：坏quantity在导出前拒绝，正确产品结果与普通unstructure一致。
- **异常／边界验收**：容器嵌套、子类策略、Any、递归对象图、用户hook输出类型、属性访问抛错。
- **原生回归**：`tests/test_unstructure.py`、`tests/test_validation.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 14．抽象PathLike字段的明确文本策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/417)；跨平台的文件记录把字段注解为os.PathLike，JSON应获得路径文本。
- **原版现状／已有替代**：PathRecord(Path(...))的JSON dumps实跑TypeError；Path具体注解已有str钩子，不冒充具体Path缺失。
- **交付与影响模块**：增加面向os.PathLike[str]的预配置钩子与明确抽象读入目标策略，使用os.fspath。；`src/cattrs/converters.py`、`src/cattrs/preconf/json.py`。
- **兼容边界**：不自动读取文件；PathLike[bytes]不静默按默认编码解码；抽象接口无法实例化时读入需指定目标。
- **正常验收**：抽象str路径注解导出/tmp/file，用户自定义__fspath__正常工作。
- **异常／边界验收**：bytes路径、错误__fspath__返回值、PurePath、路径子类、空路径和已有用户hook。
- **原生回归**：`tests/test_preconf.py`、`tests/test_unstructure.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 15．根原始类型转换错误保留目标类型

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/401)；表单直接把一个值结构为int，错误格式器仍需知道期望int。
- **原版现状／已有替代**：实跑Converter.structure(bad,int)失败后，transform_error自定义格式器收到type=None；字段错误已有note可传类型。
- **交付与影响模块**：提供显式root_type参数或结构错误包装，为根转换保留目标类型，不从异常文本猜测。；`src/cattrs/v.py`、`src/cattrs/converters.py`、`src/cattrs/errors.py`。
- **兼容边界**：普通ValueError兼容；保留原cause；根type只在明确提供或本库包装时使用。
- **正常验收**：根int失败格式器收到int，已有嵌套字段类型保持准确。
- **异常／边界验收**：自定义hook异常、无目标信息、Union、TypeAlias和空异常args。
- **原生回归**：`tests/test_v.py`、`tests/test_structure.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 16．生成与实际覆盖规则一致的数据交换Schema

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/397)；下游表单希望从attrs/dataclass声明得到可审阅的JSON Schema。
- **原版现状／已有替代**：公开导出无schema入口，src无schema生成器；外部attrs-jsonschema可做替代但不了解本converter规则。
- **交付与影响模块**：新增可选schema模块，先支持受限标准类型、attrs/dataclass、required/default/alias和注册类型schema扩展。；`src/cattrs/converters.py`、`src/cattrs/gen/__init__.py`、`src/cattrs/_compat.py`。
- **兼容边界**：不宣称任意hook都能推导schema；有自定义opaque hook且无schema声明时显式不支持。
- **正常验收**：Product及Order生成可验证的嵌套schema，required/default/rename与实际输出对应。
- **异常／边界验收**：递归refs、Union/Literal、Decimal策略、init=False、导出/读入schema区别和无法JSON表示的默认值。
- **原生回归**：`tests/test_gen_dict.py`、`tests/test_dataclasses.py`、`tests/test_recursive.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 17．嵌套字段可显式双向扁平化

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/352)；业务表格希望Product的name/quantity直接与外层label并列。
- **原版现状／已有替代**：原版Flat导出product嵌套字典，override无flatten参数；可以手写双向hook。
- **交付与影响模块**：增加明确flatten字段override，将嵌套记录映射到同一对象并在结构时按字段集合重新组合。；`src/cattrs/gen/__init__.py`、`src/cattrs/gen/_consts.py`。
- **兼容边界**：仅显式字段启用；必须检测输出键冲突，不按最后覆盖默默丢值。
- **正常验收**：Flat(Product(tea,2),order)导出name/quantity/label并可往返。
- **异常／边界验收**：重复键、Optional嵌套、默认空对象、alias、forbid_extra_keys、两层flatten和缺失子字段。
- **原生回归**：`tests/test_gen_dict.py`、`tests/test_validation.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 18．已配置标签联合可选择应用到子集

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/348)；服务的窄接口只接受A|B，但要沿用A|B|C的标签格式。
- **原版现状／已有替代**：实跑同一个A：大联合有_type，子联合没有；tagged strategy只注册精确union。
- **交付与影响模块**：新增allow_subset选项或显式派生配置，重用父标签并限制结构可接受的成员。；`src/cattrs/strategies/_unions.py`。
- **兼容边界**：普通精确联合不变；子集读入不得偷偷接收C；多个父联合策略冲突要明确。
- **正常验收**：A|B导出仍带既定A标签，A/B输入往返，C标签被拒绝。
- **异常／边界验收**：Union顺序、单成员、Optional、不同tag_name、用户钩子以及父规则后变更。
- **原生回归**：`tests/strategies/test_tagged_unions.py`、`tests/test_unions.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 19．每次结构转换显式传递业务上下文

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/232)；同一converter按每次请求的本地化或版本选择日期和字段解析规则。
- **原版现状／已有替代**：structure签名只有obj/cl；可以用闭包绑定整个converter或自定义应用wrapper，没有每次调用的显式context。
- **交付与影响模块**：新增受限上下文hook协议及structure上下文参数，贯穿嵌套生成handler与后端loads。；`src/cattrs/converters.py`、`src/cattrs/gen/__init__.py`。
- **兼容边界**：旧hook不接收额外参数；缓存只缓存规则不捕获某次context；不使用进程全局变量。
- **正常验收**：两个并发任务传不同locale，同一converter各自生成正确日期且不串值。
- **异常／边界验收**：缺context、嵌套容器、递归、异常恢复、copy、用户hook与显式默认上下文。
- **原生回归**：`tests/test_factory_hooks.py`、`tests/test_recursive.py`、`tests/test_preconf.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

## 20．泛型信封按外层判别字段路由负载

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-attrs/cattrs/issues/651)；Envelope[A]|Envelope[B]共享运行类，外层type决定payload应结构为何种类型。
- **原版现状／已有替代**：已实跑给定自定义tag_generator仍在导出KeyError Envelope；runtime class无法匹配参数化alias键。当前PEP695联合alias本身已支持，不重复计入。
- **交付与影响模块**：新增显式信封联合策略：用判别值映射参数化目标并按目标payload类型生成双向handler。；`src/cattrs/strategies/_unions.py`、`src/cattrs/converters.py`、`src/cattrs/_generics.py`。
- **兼容边界**：不凭payload形状猜外层tag；标签字段是模型真实字段时不得删除覆盖；普通tagged union保持。
- **正常验收**：a信封结构为Envelope[A]并导出同一type及A负载，b对应B，往返不丢字段。
- **异常／边界验收**：未知/重复tag、泛型默认值、已有type字段、嵌套信封、alias和Optional负载。
- **原生回归**：`tests/strategies/test_tagged_unions.py`、`tests/test_generics.py`。
- **实际依赖／步骤依赖**：沿用attrs与typing-extensions运行依赖；场景涉及的预配置后端采用已冻结可选包，不新增服务。；无。

每步包含实现、测试、文档和失败修复，同一缺陷矩阵不拆步。未来在同一真实工程累计修改，控制端冻结独立断言、核对候选加载路径、实际业务效果及原生和此前所有能力回归；研究报告不是冻结验收。
