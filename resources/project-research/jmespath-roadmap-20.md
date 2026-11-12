# JMESPath.py：二十步真实工程迭代路线

固定 [jmespath/jmespath.py@2812594e69d43098ef60f81f4efc404c071b0418](https://github.com/jmespath/jmespath.py/tree/2812594e69d43098ef60f81f4efc404c071b0418)，详见[单仓审查](./jmespath.md)。共 20 步：15 项增强提案、5 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．容器相等比较保留 JSON 布尔类型（问题修复）

- 来源／场景：https://jmespath.org/specification.html#equality-operators
- 原版现状：_equals只在顶层特殊处理bool/0/1，嵌套数组[true]与[1]当前相等，而标量true与1不相等。
- 交付目标：递归按JSON类型比较容器，并让contains数组包含判断复用一致语义。
- 影响模块：jmespath/visitor.py:_equals；functions.py:_func_contains
- 兼容边界：字符串/数字/空值与对象无序键规则遵守原规范；不把bool视为number。
- 正常验收：[true]与[1]、{a:false}与{a:0}不相等，真正同值容器仍相等。
- 异常／边界：深层数组/字典混合、空结构、contains及递归深度预算保持一致。
- 原生回归：tests/compliance/filters.json；test_search.py/test_functions.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．可变参数函数校验全部参数（问题修复）

- 来源／场景：[jmespath/functions.py:_validate_arguments/_type_check](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/functions.py)
- 原版现状：签名校验只遍历signature长度；merge({},5)的第二参数未检查，原生TypeError泄漏。
- 交付目标：variadic最后一项类型约束应用到全部剩余实参，输出JMESPathTypeError。
- 影响模块：Functions._validate_arguments/_type_check；exceptions.py
- 兼容边界：正常merge、not_null行为和最少参数数量不变；自定义variadic函数同样校验。
- 正常验收：merge({},5)报invalid-type；多字典merge正确保留后者覆盖规则。
- 异常／边界：只传最少参数、0参数、第三/第四参数错误、空types签名和expref类型。
- 原生回归：tests/test_functions.py/test_custom_functions.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．编译字面量不受调用方修改污染（问题修复）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/318
- 原版现状：visit_literal直接返回AST中的list/dict；第一次search结果append后，后续同表达式从全局缓存得到被修改值。
- 交付目标：每次求值为可变JSON字面量提供独立值，避免改变编译AST或其他查询。
- 影响模块：visitor.py:visit_literal；parser.py:ParsedResult/缓存
- 兼容边界：普通字段查询仍可返回输入引用，额外copy结果是另一显式选项；字符串/数字无需复制。
- 正常验收：编译`[1,2]`的首次结果增加3，第二次仍严格为[1,2]。
- 异常／边界：嵌套字典、同一字面量在projection重复求值、custom function修改参数和跨线程查询。
- 原生回归：tests/test_search.py/test_parser.py；compliance/literal.json
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．词法 token 统一使用绝对半开区间（问题修复）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/380
- 原版现状：foo."bar"的quoted_identifier当前start=4/end=4，literal和双字符运算符也存在长度/绝对位置混用。
- 交付目标：所有token end表示原表达式绝对结束偏移，统一诊断与切片定位。
- 影响模块：lexer.py:_consume_literal/_consume_quoted_identifier/_consume_raw_string_literal/_match_or_else/tokenize
- 兼容边界：不改变token type/value或语言求值；偏移按Python字符串字符索引定义。
- 正常验收：每个token的原始片段可由expression[start:end]正确提取，末尾引号计入。
- 异常／边界：表达式末尾、转义引号/反斜线、Unicode、多行及eof空区间。
- 原生回归：tests/test_lexer.py/test_parser.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．异类排序比较返回受控空结果（问题修复）

- 来源／场景：[jmespath/visitor.py:visit_comparator；官方比较运算规范](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/visitor.py)
- 原版现状：字符串和number单独均被_is_comparable接受，却直接跨类型operator.gt；混合值过滤当前TypeError。
- 交付目标：比较前确认兼容类型；不同JSON类型排序关系按规范得到null并由filter排除。
- 影响模块：visitor.py:_is_comparable/visit_comparator
- 兼容边界：保留该实现已支持的字符串对字符串排序，JSON数值排除bool；不做隐式字符串转数字。
- 正常验收：[?value > `1`]处理数字/字符串/空值混合数组，无TypeError，只有合格数字进入结果。
- 异常／边界：正负数、bool、两字符串、对象/数组、eq/ne深比较沿第01步。
- 原生回归：tests/test_search.py；compliance/filters.json
- 真实依赖：01

## 06．命令行输入和表达式错误统一诊断（增强提案）

- 来源／场景：[bin/jp.py:main；smoke的空表达式Traceback](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/bin/jp.py)
- 原版现状：空表达式未被现有except覆盖，--ast编译在try之外，JSON读取错误也直接Traceback。
- 交付目标：CLI统一报告输入JSON/表达式/函数错误代码、简短原因及非零退出，支持可选结构化诊断。
- 影响模块：bin/jp.py；exceptions.py
- 兼容边界：正常输出和现有invalid-arity/type/function/syntax文字兼容；不吞掉未知内部错误。
- 正常验收：空表达式、--ast语法错、坏JSON分别有可识别诊断，stdout不混错误。
- 异常／边界：文件不存在/编码错误、破管道、Unicode多行定位与--debug保留堆栈。
- 原生回归：新增CLI测试；tests/test_parser.py/test_lexer.py
- 真实依赖：04

## 07．编译查询可绑定求值选项（增强提案）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/181
- 原版现状：compile只接expression，ParsedResult.search每次再传Options，易漏custom_functions/dict_cls。
- 交付目标：compile允许绑定不可变配置快照，search可显式覆盖，缓存仅共享与选项无关的AST。
- 影响模块：__init__.py:compile；parser.py:ParsedResult；visitor.Options
- 兼容边界：原compile(expression)与search(value,options)保持；不把绑定配置写入全局AST缓存。
- 正常验收：同一表达式可分别绑定不同函数集合和OrderedDict，互不污染。
- 异常／边界：选项后续被修改的规则、显式None覆盖、自定义函数有状态、并发调用隔离。
- 原生回归：test_parser.py/test_custom_functions.py/test_search.py
- 真实依赖：03

## 08．命名查询集一次编译并逐项返回状态（增强提案）

- 来源／场景：__init__.py:search；库存多字段导出实际场景；固定源码：[jmespath/exceptions.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/exceptions.py)。
- 原版现状：单表达式多选对象已存在，但多个独立命名查询的编译错误/运行错误不能逐项隔离。
- 交付目标：提供QuerySet编译命名表达式清单，返回每项值或结构化错误，支持fail_fast。
- 影响模块：新增查询集入口；parser.ParsedResult；exceptions.py
- 兼容边界：不改现有多选hash语义；错误不能写成普通null冒充缺失值。
- 正常验收：同一库存同时返回低库存表/总量，第三个类型错误独立记录。
- 异常／边界：重复名称、空查询集、编译期错误、函数副作用调用次数与fail_fast顺序。
- 原生回归：tests/test_search.py/test_functions.py
- 真实依赖：06, 07

## 09．惰性查询文档迭代器（增强提案）

- 来源／场景：parser.py:ParsedResult.search；逐条处理事件文档场景；固定源码：[jmespath/parser.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/parser.py)。
- 原版现状：已有projection只操作已加载的list，无对文档迭代器逐条应用编译查询的公共入口。
- 交付目标：search_iter消费单次迭代器，逐条产出查询结果和可选文档序号错误。
- 影响模块：新增search_iter；ParsedResult.search
- 兼容边界：逐文档惰性不宣称单文档内部投影恒定内存；不改变list输入的标准语言语义。
- 正常验收：读取生成器前三条结果仅消费三条文档，复用一次编译查询。
- 异常／边界：输入生成器抛错、空输入、continue/stop错误政策、None合法结果与提前关闭。
- 原生回归：tests/test_search.py及计数生成器场景
- 真实依赖：07

## 10．缺失字段诊断保持标准 null 语义（增强提案）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/204
- 原版现状：missing字段和显式null都返回None，最终结果无法告诉配置校验方哪一层不存在。
- 交付目标：增加独立diagnostics模式收集缺失字段/索引路径与表达式位置，返回值继续遵守标准null。
- 影响模块：visitor.py:visit_field/visit_index；Options；诊断结果类型
- 兼容边界：默认不追踪；不得把Missing新类型泄漏到标准函数和JSON输出。
- 正常验收：a:null和缺a查询结果都是null，诊断仅后者记录missing。
- 异常／边界：projection自动省略null、or短路、越界负索引、重复访问去重及数量上限。
- 原生回归：test_search.py；compliance/indices.json
- 真实依赖：04

## 11．投影结果可追溯输入位置（增强提案）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/214
- 原版现状：projection会省略null并重排，结果没有原始数组索引；用户难把异常行定位回输入。
- 交付目标：提供search_with_paths，为直接字段/索引/投影保留来源路径，派生表达式明确标记computed。
- 影响模块：visitor.py各projection/comparator；独立追踪结果类型
- 兼容边界：不把追踪元数据混入标准结果；首版列清支持节点，函数派生值不捏造唯一来源。
- 正常验收：过滤出items[2].sku能回溯原索引2，sort_by之后关联仍正确。
- 异常／边界：多来源merge、字面量、相同值、空值省略和unsupported表达式显式状态。
- 原生回归：tests/test_search.py；projection/filter compliance
- 真实依赖：10

## 12．查询执行的节点和输出预算（增强提案）

- 来源／场景：visitor.py:visit_projection/visit_flatten/_Expression；大事件查询场景；固定源码：[jmespath/visitor.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/visitor.py)。
- 原版现状：每个节点和输出集合无限制执行，嵌套map/projection可能产生超大中间结果。
- 交付目标：Options增加max_visits/max_output_items，受控预算错误包含表达式位置并支持取消回调。
- 影响模块：Visitor.visit；TreeInterpreter集合生成；Options
- 兼容边界：默认不限；预算耗尽不得伪装成合法截断查询结果，计数不能只覆盖最终输出。
- 正常验收：小预算查询受控失败，大预算结果与原查询一致，取消可停止长投影。
- 异常／边界：短路表达式、nested map、custom function不透明工作量明确限制、精确边界。
- 原生回归：test_search.py/test_functions.py/test_custom_functions.py
- 真实依赖：04

## 13．稳定的只读 AST 检查格式（增强提案）

- 来源／场景：bin/jp.py --ast；ParsedResult._render_dot_file内部接口；固定源码：[bin/jp.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/bin/jp.py)、[jmespath/parser.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/parser.py)、[jmespath/ast.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/ast.py)。
- 原版现状：--ast目前pformat私有字典结构，无法稳定消费；公开说明AST是内部细节。
- 交付目标：提供版本化explain格式，输出节点种类、源码区间、子节点及函数需求，不暴露可变缓存AST。
- 影响模块：parser.py；ast.py；lexer跨度；bin/jp.py
- 兼容边界：私有parsed结构不作为新稳定契约；默认查询不额外保存完整解析跟踪。
- 正常验收：同一过滤查询输出合法JSON且节点区间可对应源片段，编辑输出不影响后续查询。
- 异常／边界：字面量脱敏、Unicode、括号/省略索引、未知格式版本与语法错误诊断。
- 原生回归：tests/test_parser.py/test_lexer.py
- 真实依赖：03, 04

## 14．可配置表达式缓存与命中统计（增强提案）

- 来源／场景：parser.py:Parser._CACHE/_MAX_SIZE/purge；固定源码：[jmespath/parser.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/parser.py)。
- 原版现状：已有全局512缓存和purge，但大小不可实例配置、无命中统计或禁用入口。
- 交付目标：提供显式Cache对象可禁用/限量/统计，并允许每个查询服务隔离缓存。
- 影响模块：Parser.parse/purge；compile/search入口
- 兼容边界：默认保留512级缓存效果；缓存只存AST，不保留输入数据、绑定选项和查询结果。
- 正常验收：两个独立缓存容量2/0互不影响，命中与淘汰计数可解释。
- 异常／边界：并发编译同表达式、purge统计规则、超长表达式和上限0不能增长。
- 原生回归：tests/test_parser.py缓存/线程测试
- 真实依赖：07, 13

## 15．组合自定义函数注册表并检测冲突（增强提案）

- 来源／场景：README.rst自定义Functions；FunctionRegistry._populate_function_table；固定源码：[README.rst](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/README.rst)、[jmespath/functions.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/functions.py)。
- 原版现状：继承类能定义函数，但跨独立插件集合需手工多继承；同名函数覆盖缺少声明政策。
- 交付目标：提供compose_functions显式组合多个函数集合，冲突error/override可选并输出有效签名清单。
- 影响模块：functions.py:FunctionRegistry/Functions；Options
- 兼容边界：默认标准函数集合不变；不自动扫描/导入未知模块，保持现有装饰器签名。
- 正常验收：字符串函数集和业务聚合函数集可共用，重名默认失败并列出来源。
- 异常／边界：变参签名、非法signature、标准函数覆盖必须显式、状态化实例不共享。
- 原生回归：tests/test_custom_functions.py/test_functions.py
- 真实依赖：02, 07

## 16．可选扩展函数按表达式分组（增强提案）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/153
- 原版现状：标准函数有sort_by/map但没有group_by，按region分组库存需离开查询流程。
- 交付目标：在显式ExtendedFunctions中提供group_by(array,&key)，保留组内输入顺序。
- 影响模块：新增扩展函数集合；functions.py expref签名
- 兼容边界：属于Python可选扩展，不宣称标准JMESPath功能；默认函数表仍无group_by。
- 正常验收：按region得到各地区商品列表，后续可map生成分组统计。
- 异常／边界：键为null/数字/对象的规则明确，键碰撞、空数组和预算限制。
- 原生回归：test_custom_functions.py；分组业务验收
- 真实依赖：12, 15

## 17．可选扩展函数按业务键稳定去重（增强提案）

- 来源／场景：functions.py:sort_by/map；订单重复事件真实场景；固定源码：[jmespath/functions.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/functions.py)。
- 原版现状：没有按expref进行稳定去重的函数，sort_by不会删除重复业务键。
- 交付目标：ExtendedFunctions提供unique_by(array,&key)，明确保留first/last政策。
- 影响模块：扩展函数集合；JSON类型相等工具
- 兼容边界：不在标准Functions自动注册；不把bool和number当同一去重键。
- 正常验收：按order_id重复事件保留首条且稳定，直接值去重可用&@。
- 异常／边界：嵌套数组/对象键、None、字符串/数字不同、不可支持类型和超预算。
- 原生回归：test_custom_functions.py；第01步相等回归
- 真实依赖：01, 12, 15

## 18．可选扩展函数从键值对构造对象（增强提案）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/152
- 原版现状：多选hash的键是语法中的固定标识符，无法把动态字段列表转换为对象。
- 交付目标：ExtendedFunctions提供from_entries，将明确key/value记录转换为JSON对象并声明重复键政策。
- 影响模块：扩展函数集合；dict_cls/函数签名
- 兼容边界：只接受字符串JSON对象键，不自动将null/数字转字符串；默认语言不扩展语法。
- 正常验收：[{key:a,value:1},{key:b,value:2}]转换后可继续字段投影。
- 异常／边界：缺key/value、重复key、空字符串键、OrderedDict和嵌套value保持。
- 原生回归：test_custom_functions.py/test_search.py
- 真实依赖：15

## 19．命令行逐条处理 JSONL 文档（增强提案）

- 来源／场景：https://github.com/jmespath/jmespath.py/issues/122
- 原版现状：jp.py一次json.load/loads整个文件，没有逐文档输入与序号错误隔离。
- 交付目标：增加--json-lines流输入，查询编译一次，每条输出一条结果，明确continue/stop政策。
- 影响模块：bin/jp.py；search_iter；CLI诊断
- 兼容边界：默认单JSON文档不变；空行政策明确，不自动猜测格式或承诺单行无限长度。
- 正常验收：三条事件得到三条JSON结果，中间坏行可按显式选项独立报错后继续。
- 异常／边界：多行pretty JSON误用、超长行、BOM、破管道、末尾无换行与null结果。
- 原生回归：CLI验收；test_search.py；search_iter累计用例
- 真实依赖：06, 09, 12

## 20．命令行面向脚本的输出和断言模式（增强提案）

- 来源／场景：bin/jp.py固定indent=4输出；Shell提取字段真实场景；固定源码：[bin/jp.py](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/bin/jp.py)。
- 原版现状：所有结果固定pretty JSON，没有raw字符串、compact输出或按空结果退出的选项。
- 交付目标：提供--raw-output/--compact/--sort-keys及--exit-status，清楚定义null/false/空数组判定。
- 影响模块：bin/jp.py输出层；CLI异常处理
- 兼容边界：默认pretty JSON及退出0保持；raw仅对字符串去引号，其他值仍合法JSON。
- 正常验收：提取sku输出无引号一行，compact可被json读回，断言库存空时返回约定非零。
- 异常／边界：字符串含换行、数字0的JMES真值、JSONL逐条状态汇总、Unicode及破管道。
- 原生回归：CLI场景；完整991项原生回归
- 真实依赖：06, 19

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
