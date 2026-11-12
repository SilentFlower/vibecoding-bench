# WTForms：二十步真实工程迭代路线

固定 [pallets-eco/wtforms@af18fd6a7595d374aa707ff97b73df0dcc462ec2](https://github.com/pallets-eco/wtforms/tree/af18fd6a7595d374aa707ff97b73df0dcc462ec2)，见[单仓审查](./wtforms.md)。19项增强与1项原版复现的调用者列表所有权修复；仅研究，未实施。新API名称均为拟议契约。

原版已有FormField/FieldList、data/obj回退、post_process、接收(form,field)的choices工厂、enum choices/coerce、disabled HTML选项、datalist、NaN范围拒绝和列表增删重排；均排除新增。每项是一个完整业务交付，代码/测试/文档/失败修复不拆步，所有业务场景使用本地合成商品数据。

## 01．按数据来源判断Optional空值

- **类型与来源**：增强提案；同一商品库存表单同时处理表单输入和已有Python数据，非空对象值仍需范围校验。
- **原版现状与证据**：01_data_aware_optional：data.quantity=99时Optional停止后续NumberRange并通过，formdata.quantity=99则失败；原Optional明确依据raw_data，这是既有约定。
- **交付目标**：增加显式data-aware Optional或presence策略，非空object_data按已处理值继续验证，区分缺失与明确空值。
- **影响模块**：src/wtforms/validators.py、src/wtforms/fields/core.py。
- **兼容边界**：默认Optional请求语义不变；0/False不得一律当缺失，字符串空白策略仍显式。
- **正常验收**：对象99在0..5范围校验失败，对象0通过，真正缺省值可跳过。
- **边界验收**：None、空白、空列表、转换错误、显式raw空值与嵌套字段的清错规则明确。
- **原生回归**：tests/validators/test_optional.py、tests/validators/test_number_range.py。
- **实际依赖**：无；沿用已有validator协议。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/842)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/validators.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)。

## 02．可等待的验证链

- **类型与来源**：增强提案；本地异步应用需要await业务校验器，同时保留同步内建规则。
- **原版现状与证据**：02_async_validation：Form/Field无validate_async，validate为同步入口；原链调用返回值没有await机制。
- **交付目标**：增加独立validate_async，按明确顺序处理同步/awaitable校验器，保持pre/post与StopValidation错误语义。
- **影响模块**：src/wtforms/form.py、src/wtforms/fields/core.py、src/wtforms/fields/form.py、src/wtforms/fields/list.py。
- **兼容边界**：同步validate保持；发现awaitable时应明确提示使用异步入口，不能静默通过；不提供HTTP客户端或自动并发所有规则。
- **正常验收**：用await asyncio.sleep(0)的本地校验器与NumberRange混合正确收集错误，嵌套表单可await。
- **边界验收**：取消、validator异常、StopValidation、extra/inline规则、嵌套FieldList和重复调用不泄漏协程。
- **原生回归**：tests/test_form.py、tests/fields/test_field.py。
- **实际依赖**：无；标准库asyncio；不访问外部业务系统。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/839)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)；[依据5](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)。

## 03．输入与展示的双向转换协议

- **类型与来源**：增强提案；金额编辑希望数据始终是Decimal，展示可格式化且不把展示前缀写回对象。
- **原版现状与证据**：03_bidirectional_filters：输入2.50经filter变5.00，但控件仍优先raw_data显示2.50；只有单向filters，没有output_filters。
- **交付目标**：新增明确input/output转换器协议或显示适配器，分别定义process后的业务值与widget展示值。
- **影响模块**：src/wtforms/fields/core.py、src/wtforms/fields/numeric.py、src/wtforms/widgets/core.py。
- **兼容边界**：现有filters与raw错误回显优先级保持默认；opt-in才使用双向协议，不重复转换已经处理的数据。
- **正常验收**：金额输入转换到标准Decimal，展示格式正确，populate_obj只写标准值。
- **边界验收**：非法输入保留用户原值、None、区域格式、重复渲染和输出转换失败有可见字段错误或明确异常。
- **原生回归**：tests/fields/test_filters.py、tests/fields/test_decimal.py、tests/test_widgets.py。
- **实际依赖**：无；本地标准库Decimal；区域格式沿用已有可选Babel。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/747)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/numeric.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/widgets/core.py)。

## 04．字段输入来源与存在性信息

- **类型与来源**：增强提案；编辑器要区分库存来自obj、data、default或此次提交，以及字段是否真的提交。
- **原版现状与证据**：04_input_provenance：已有raw_data/object_data，obj和data确可组合并按obj优先；没有source标志，不能照旧issue宣称二者无法组合。
- **交付目标**：增加只读来源枚举与provided/present标志，贯穿嵌套字段和processing cycle，保留缺省与显式None。
- **影响模块**：src/wtforms/form.py、src/wtforms/fields/core.py、src/wtforms/fields/form.py、src/wtforms/fields/list.py。
- **兼容边界**：现有数据优先级和field.data不变；原始值不必被额外复制，来源未知时明确unknown。
- **正常验收**：同表单四字段分别来自default/data/obj/formdata，标志对应真实选择。
- **边界验收**：空MultiDict、缺键、空串、False/0、再次process、prefix与嵌套来源路径稳定。
- **原生回归**：tests/test_form.py、tests/fields/test_field.py、tests/fields/test_defaults.py。
- **实际依赖**：无；独立于步骤01，可提供其依据但不构成功能依赖。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/402)；[依据2](https://github.com/pallets-eco/wtforms/issues/662)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据5](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)；[依据6](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)。

## 05．显式字段掩码验证

- **类型与来源**：增强提案；商品局部编辑只修改name，需要验证选中字段并明确未验证字段状态。
- **原版现状与证据**：05_partial_validation：validate(only=[name]) TypeError；默认全部校验导致缺失quantity失败。当前可自行派生精简Form或循环field.validate。
- **交付目标**：提供validate_fields/only/exclude模式，返回哪些字段已验证，嵌套掩码按字段路径选择。
- **影响模块**：src/wtforms/form.py、src/wtforms/fields/form.py、src/wtforms/fields/list.py。
- **兼容边界**：默认validate全量不变；不把未验证字段当有效；交叉规则缺依赖时明确延期/要求补齐。
- **正常验收**：只验证name时返回选中字段结果，quantity不被误清旧错误或标成功。
- **边界验收**：未知字段、空mask、only/exclude冲突、嵌套列表选择、inline/extra validators与全量后续验证回归。
- **原生回归**：tests/test_form.py、tests/fields/test_form.py、tests/fields/test_list.py。
- **实际依赖**：无；可独立于步骤04来源标志，调用方显式提供mask。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)。

## 06．嵌套JSON输入适配器

- **类型与来源**：增强提案；本地API工具以字典/数组表达商品规格，需要提交语义而非只作为默认数据。
- **原版现状与证据**：06_nested_json_adapter：普通嵌套dict传formdata被拒绝；data=的嵌套对象加载已经支持。没有JSONFormData适配器。
- **交付目标**：增加独立适配器，将嵌套对象/数组转换成getlist与路径协议，明确null、布尔、多值和缺失提交行为。
- **影响模块**：src/wtforms/meta.py、src/wtforms/utils.py、src/wtforms/fields/form.py、src/wtforms/fields/list.py。
- **兼容边界**：不自动把任意dict当formdata；旧data/obj与MultiDict路径保持；避免把JSON结构和纯字符串值混为同一编码。
- **正常验收**：product.label与variants两项按提交语义处理，错误定位到正确嵌套字段。
- **边界验收**：字段名含分隔符、空数组、null、混合数组、未知键和重复路径冲突明确拒绝或有稳定策略。
- **原生回归**：tests/test_form.py、tests/fields/test_form.py、tests/fields/test_list.py。
- **实际依赖**：无；标准库容器，不引入Web框架依赖。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/198)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/meta.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/utils.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)；[依据5](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)。

## 07．保留继承行为的动态Form派生

- **类型与来源**：增强提案；配置化商品编辑器按场景添加少量字段，同时保留现有Meta和inline规则。
- **原版现状与证据**：07_dynamic_form_schema：Form实例增加字段明确TypeError；BaseForm和动态type()已有替代，不能宣称完全不能动态建表单。
- **交付目标**：提供with_fields/derive工厂返回独立派生Form类，显式增加/覆盖/删除字段并保留定义的验证、Meta和顺序。
- **影响模块**：src/wtforms/form.py、src/wtforms/fields/core.py。
- **兼容边界**：不允许默默改变现有实例；原父类及其缓存不变，字段名冲突和覆盖策略明确。
- **正常验收**：从ProductForm派生带note的类，父类仍只有两字段，父级inline规则和Meta继续生效。
- **边界验收**：多重继承、同名覆盖、删除继承字段、两个派生类并存及反复实例化顺序稳定。
- **原生回归**：tests/test_form.py、tests/fields/test_field.py。
- **实际依赖**：无；标准库类构造；不依赖新schema导出。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/736)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)。

## 08．带代码与路径的结构化验证问题

- **类型与来源**：增强提案；本地表单/JSON消费者需要稳定错误代码与参数，不解析翻译后的文案。
- **原版现状与证据**：08_structured_issues：现errors是字段到字符串列表/嵌套容器，ValidationError只保留消息，没有标准issues。
- **交付目标**：新增ValidationIssue(code,path,message,params,phase)及只读聚合API，内建规则填稳定代码，旧errors仍投影为文本。
- **影响模块**：src/wtforms/validators.py、src/wtforms/fields/core.py、src/wtforms/form.py、src/wtforms/fields/form.py、src/wtforms/fields/list.py。
- **兼容边界**：现有自定义ValidationError(message)兼容为generic代码；不改变本地化信息，不把message字符串当稳定代码。
- **正常验收**：必填与范围错误分别有代码/参数，嵌套规格的路径可准确定位。
- **边界验收**：process/pre/普通/post错误、StopValidation无消息、列表索引与表单级错误不遗漏或重复。
- **原生回归**：tests/validators/test_validators.py、tests/fields/test_field.py、tests/test_form.py。
- **实际依赖**：无；标准库记录对象；原生测试路径以实际仓库为准。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/validators.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)；[依据5](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)。

## 09．声明式跨字段业务规则

- **类型与来源**：增强提案；商品预订起止日期和库存组合需要一个表单级规则，关联多个字段显示同一原因。
- **原版现状与证据**：09_cross_field_rules：已有EqualTo和自定义Form.validate覆写，无通用rules声明；form_errors可人工写入。
- **交付目标**：新增Form规则声明，列出依赖字段、执行条件与错误目标，单次处理后按明确顺序执行并支持表单级错误。
- **影响模块**：src/wtforms/form.py、src/wtforms/validators.py。
- **兼容边界**：现有单字段与inline规则保持；依赖字段解析失败时可配置跳过，避免制造重复业务错误。
- **正常验收**：start<=end以及quantity/available组合各报告到指定字段或form，成功无附加错误。
- **边界验收**：依赖缺失、partial mask、规则抛错、重复validate、继承覆盖和多目标错误去重回归。
- **原生回归**：tests/test_form.py、tests/validators/test_validators.py。
- **实际依赖**：无；可通过旧ValidationError落地，步骤08结构化问题为可选增强。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/validators.py)。

## 10．可选择的验证过程诊断

- **类型与来源**：增强提案；维护者需要解释为什么规则未执行、数据在哪阶段转换或验证停止。
- **原版现状与证据**：10_validation_trace：原版有raw_data/process_errors/errors，但没有validation_trace；pre/chain/post的实际路径需调试器逐步跟踪。
- **交付目标**：提供opt-in诊断回调/trace，记录字段路径、阶段、规则名、执行/跳过/停止及耗时，不默认保存值。
- **影响模块**：src/wtforms/fields/core.py、src/wtforms/form.py。
- **兼容边界**：默认无跟踪开销；诊断不改变校验顺序，不能靠trace回调自行更改错误结果。
- **正常验收**：Optional停止后trace标明后续NumberRange未执行，非法整数可定位process阶段。
- **边界验收**：trace回调异常、nested form、partial validation、零规则和多轮validate的事件边界清楚。
- **原生回归**：tests/fields/test_field.py、tests/test_form.py。
- **实际依赖**：无；标准库计时；独立于结构化问题API。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)。

## 11．流式批量表单验证

- **类型与来源**：增强提案；本地CSV商品导入需要逐行验证和完整行号，不因首行错误停止整批。
- **原版现状与证据**：11_batch_validation：没有类级validate_many；本轮手工循环得到[True,False]，当前应用需自行包装错误/行号。
- **交付目标**：增加独立batch iterator，输入记录和Form类，逐项产出数据/错误/输入序号，支持显式fail-fast与最大错误预算。
- **影响模块**：src/wtforms/form.py。
- **兼容边界**：不复用同一个可变Form实例污染行间状态；不读取完整输入，不能把batch结果视为已写对象。
- **正常验收**：三条记录按输入次序返回一项错误与两项成功，原输入不变，首结果无需消费全部生成器。
- **边界验收**：空输入、构造器异常、行号起点、超预算、对象/JSON适配选择及取消生成器清理明确。
- **原生回归**：tests/test_form.py。
- **实际依赖**：无；标准库迭代器；不依赖步骤06，可由调用方提供适配工厂。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)。

## 12．对象填充的变更预览

- **类型与来源**：增强提案；本地管理工具先展示商品对象将被改哪些字段，再由调用者决定写入。
- **原版现状与证据**：12_population_preview：populate_obj遇quantity setter失败前name已改；该顺序写入有明确文档，按新增预览能力处理。
- **交付目标**：提供population_plan/changes，只读取目标已有值并构造有序字段变更，不调用setter；应用可明确选择之后执行旧populate或自身事务。
- **影响模块**：src/wtforms/form.py、src/wtforms/fields/core.py、src/wtforms/fields/form.py、src/wtforms/fields/list.py。
- **兼容边界**：不承诺任意Python对象全局事务；默认populate_obj不变；目标属性读取异常也必须清楚报告。
- **正常验收**：name/quantity差异列出old/new与字段路径，预览后目标字节/属性不变。
- **边界验收**：缺属性、None、嵌套对象、列表、未验证字段和只读property明确支持范围，不执行属性setter探测。
- **原生回归**：tests/test_form.py、tests/fields/test_form.py、tests/fields/test_list.py。
- **实际依赖**：无；标准库数据结构；不要求先实现部分验证。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)。

## 13．带辅助说明与错误关联的字段渲染

- **类型与来源**：增强提案；普通商品表单需要label、说明和错误与输入关联，减少每页重复组装无障碍属性。
- **原版现状与证据**：13_accessible_field_group：当前field()只输出input，description/errors已有数据但没有render_group；aria_*可手工传入且已支持。
- **交付目标**：提供opt-in字段组渲染器/可覆写模板协议，生成唯一help/error id，关联aria-describedby/aria-invalid，保留显式调用者属性。
- **影响模块**：src/wtforms/widgets/core.py、src/wtforms/fields/core.py、src/wtforms/meta.py。
- **兼容边界**：默认单控件HTML不变；不强加CSS框架；label与文本转义沿用现有约定。
- **正常验收**：错误name字段生成关联label/help/error，aria-invalid与实际错误一致，正常字段不挂无效错误id。
- **边界验收**：prefix、同页两表单、隐藏字段、checkbox/radio组、多条错误和自定义widget兼容。
- **原生回归**：tests/test_widgets.py、tests/fields/test_label.py、tests/test_form.py。
- **实际依赖**：无；MarkupSafe为已有依赖；不引入模板引擎。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/widgets/core.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/meta.py)。

## 14．disabled选项的显式业务校验策略

- **类型与来源**：增强提案；某个商品分类暂不可用，应用希望显示disabled且按明确策略不接受此次新选择。
- **原版现状与证据**：14_disabled_choice_policy：SelectChoice.render_kw.disabled已正确渲染，提交closed仍validate=True；当前validate_choice只检查值是否存在。
- **交付目标**：新增独立的disabled/availability语义或拒绝策略，与纯HTML render_kw分离，允许既有选中值与新选择采取明确不同规则。
- **影响模块**：src/wtforms/fields/choices.py、src/wtforms/widgets/core.py。
- **兼容边界**：不把已有disabled呈现算新增；默认兼容旧render_kw不参与验证；规则是业务可选性，不声称替代外部权限控制。
- **正常验收**：启用策略后新选closed失败、open通过，原已保存closed的只读展示按所选规则处理。
- **边界验收**：多选、optgroup、动态choices、coerce、disabled全部选项和旧object_data可用性回归。
- **原生回归**：tests/fields/test_select.py、tests/fields/test_selectmultiple.py、tests/test_widgets.py。
- **实际依赖**：无；现有SelectChoice/Choice协议。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/928)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/choices.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/widgets/core.py)。

## 15．以业务键标识的FieldList

- **类型与来源**：增强提案；可重新排序的商品规格行要按稳定规格id关联原对象，避免只按位置对齐。
- **原版现状与证据**：15_keyed_field_list：variants-3/7在处理后重编号0/1；当前FieldList已支持insert/pop/reindex，但没有keyed列表。
- **交付目标**：新增独立KeyedFieldList或显式key参数，区分显示位置与稳定业务键，输出顺序/对象匹配/错误路径包含键。
- **影响模块**：src/wtforms/fields/list.py、src/wtforms/fields/form.py。
- **兼容边界**：原FieldList整数索引语义保持；不自动信任输入键去查数据库，调用者提供明确已有对象映射。
- **正常验收**：交换两个规格顺序后仍关联各自原对象和错误，输出列表顺序按提交约定。
- **边界验收**：重复键、缺失键、新增/删除行、空键、分隔符、max_entries和嵌套键路径明确。
- **原生回归**：tests/fields/test_list.py、tests/fields/test_form.py。
- **实际依赖**：无；只做内存键映射，不添加持久化层。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/list.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/form.py)。

## 16．多值数据的逐项验证组合器

- **类型与来源**：增强提案；多选标签或多文件元数据的列表值需要复用普通标量规则并准确定位项。
- **原版现状与证据**：16_each_validator：无Each；FieldList本来逐子field验证，SelectMultipleField等的field.data却是整个列表，应用需自行包装。
- **交付目标**：提供Each(validator,extractor=...)组合器，为列表中每项建立明确只读字段视图并聚合索引错误，支持提取普通文件名等业务值。
- **影响模块**：src/wtforms/validators.py、src/wtforms/fields/core.py。
- **兼容边界**：不改变FieldList既有子字段验证；不默认把str按字符列表处理，错误值与原数据不互相覆盖。
- **正常验收**：三个标签中两项满足Length，一项错误指向实际索引，原列表完整不变。
- **边界验收**：None、空列表、生成器、提取器异常、StopValidation逐项/整体边界及嵌套Each的路径明确。
- **原生回归**：tests/validators/test_validators.py、tests/fields/test_selectmultiple.py、tests/fields/test_file.py。
- **实际依赖**：无；现有validator与字段视图；不访问真实文件内容。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/issues/442)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/validators.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)。

## 17．可选择的首错停止策略

- **类型与来源**：增强提案；本地校验中一条基础规则失败后可选择不继续昂贵的后续业务校验。
- **原版现状与证据**：17_fail_fast_policy：首个ValidationError后second仍执行；StopValidation已可手写短路，但Field构造没有bail策略。
- **交付目标**：增加显式field/form fail-fast策略，区分字段内停止与全表停止，保留已收集错误与post_validate状态。
- **影响模块**：src/wtforms/fields/core.py、src/wtforms/form.py。
- **兼容边界**：默认累积错误保持；不把所有ValidationError改成StopValidation；pre/process错误是否跳过链明确配置。
- **正常验收**：bail字段首错后second调用0，非bail仍执行；post hook收到实际停止原因。
- **边界验收**：extra/inline规则、Optional、process错误、nested fields、无消息停止与再次验证状态重置回归。
- **原生回归**：tests/fields/test_field.py、tests/test_form.py、tests/validators/test_validators.py。
- **实际依赖**：无；可独立于异步验证，组合路径另测。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)。

## 18．继承表单的显式字段顺序

- **类型与来源**：增强提案；商品编辑器希望备注提前展示而不重写字段声明或改变字段创建计数。
- **原版现状与证据**：18_explicit_field_order：Meta.field_order声明note/quantity/name被忽略，实际按name/quantity/note；默认顺序来自creation_counter。
- **交付目标**：新增显式字段顺序接口/Meta选项，允许列出部分字段，未列字段按原稳定顺序追加。
- **影响模块**：src/wtforms/form.py。
- **兼容边界**：默认创建顺序保持；同名覆盖和多重继承规则清楚，不改变HTML name或字段id。
- **正常验收**：指定note最前时迭代/控件组顺序一致，未列字段按原顺序补齐。
- **边界验收**：未知名称、重复名称、删除字段、prefix、动态派生与缓存刷新不影响父类。
- **原生回归**：tests/test_form.py。
- **实际依赖**：无；稳定排序；独立于步骤07动态类工厂。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)。

## 19．机器可读的字段说明清单

- **类型与来源**：增强提案；本地表单编辑器需统一读取字段类型、标签、约束和候选，避免扫描widget HTML。
- **原版现状与证据**：19_form_schema_export：label/flags/choices可人工读取，Form无to_schema聚合入口；不宣称数据不可内省。
- **交付目标**：提供版本化字段manifest，描述受支持类型、标签、required/length/range/choices与嵌套结构；动态约束标成动态或显式快照。
- **影响模块**：src/wtforms/form.py、src/wtforms/fields/core.py、src/wtforms/fields/choices.py、src/wtforms/validators.py。
- **兼容边界**：这是WTForms字段说明而非完整JSON Schema/数据库schema；不执行任意callable来猜约束，不把未知规则伪造成可表达约束。
- **正常验收**：普通商品字段manifest可JSON序列化，范围与必填信息和实际规则一致，嵌套规格有路径。
- **边界验收**：自定义字段/validator、动态choices、翻译标签、重复表单、非序列化default和循环Form引用有显式未知/引用标记。
- **原生回归**：tests/test_form.py、tests/fields/test_field.py、tests/fields/test_select.py。
- **实际依赖**：无；标准库序列化与已有公开元数据。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)；[依据2](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/core.py)；[依据3](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/fields/choices.py)；[依据4](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/validators.py)。

## 20．不修改调用者的附加规则列表

- **类型与来源**：复现修复提案；多个表单共享extra_filters/extra_validators定义时，inline规则不应被不断追加进调用者列表。
- **原版现状与证据**：20_caller_list_ownership：两次构造后shared_filters.value由空变长2，两次validate后shared_validators.value也长2；源码只浅拷贝dict再append到原list。
- **交付目标**：在组合inline规则前复制每个被使用的sequence，确保本轮添加只属于本轮表单/验证链；同时修process和validate同根问题。
- **影响模块**：src/wtforms/form.py。
- **兼容边界**：附加规则执行顺序保持extra在前inline在后；不就地清空调用者已有规则，不深拷贝callable或改变其身份。
- **正常验收**：共享两个空列表多次构造/validate后仍为空，每个inline只在本轮执行一次。
- **边界验收**：tuple/generator或只读sequence的支持范围、多个字段、异常inline、无对应field与重复validate回归；两种症状只计一个所有权修复。
- **原生回归**：tests/test_form.py、tests/fields/test_filters.py。
- **实际依赖**：无；标准库sequence复制。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/pallets-eco/wtforms/blob/af18fd6a7595d374aa707ff97b73df0dcc462ec2/src/wtforms/form.py)。

## 独立验收与累计回归

未来控制端冻结原生Form/Field/validator/widget调用，核对processed data、错误内容/路径、实际对象赋值、HTML关联、调用次数与原输入未被修改。异步/批量场景用本地受控协程与生成器；每步累计回归关联原生测试及此前交付。完整原版537通过不等于本路线新契约通过；冻结用例、离线依赖准备与平台接入未完成。
