# Cerberus：二十步原生工程路线

固定 [pyeve/cerberus@83f5dada76aa3179ef21b677a7f4235bf20c1566](https://github.com/pyeve/cerberus/tree/83f5dada76aa3179ef21b677a7f4235bf20c1566)，1.3.8。前两项已复现，十八项增强已核对当前规则／入口与使用场景；没有把所有旧issue或约定差异称为bug。原版观察在 `.deploy/github-100-research/core-utils/cerberus/observations-result.json`。

各步含实现、文档与正反验收，统一运行上游 `python -m pytest cerberus/tests` 累计回归。模块相对cerberus/；测试相对cerberus/tests/。新增入口名仅为提案，尚未实现或获上游接受。已有check_with、自定义Validator子类、命名coercer/default_setter、schema/rules注册表、ErrorList与错误树可以手工组合很多能力，路线明确保留这些替代；不重写成统一app.py。除说明的组合边界外，各项可独立交付。

## 01．逻辑子schema不能绕过readonly（修复）

- 来源：[官方 #297](https://github.com/pyeve/cerberus/issues/297)，validator.py的__validate_logical/_validate_readonly与已归一化状态。相同record直接schema拒绝id输入，oneof_schema却实际返回True。
- 交付：区分真正已检查readonly与仅继承归一化状态，逻辑分支按实际schema检查；默认值生成readonly字段的合法路径保留。
- 验收：oneof/anyof/allof/noneof、嵌套、purge_readonly、default+readonly、normalize=False；test_validation.py／test_normalization.py。四类逻辑算一个一致性修复。

## 02．字段重命名不因中间删除丢值或崩溃（修复）

- 来源：validator.py:_normalize_rename/_normalize_rename_handler。原版rename:'x'作用于x会删除值；同时设置rename与handler会因读取已删除的旧键而KeyError。
- 交付：先确定重命名计划再提交，identity保留原值；同时设置两种改名手段时明确组合顺序或schema阶段清楚拒绝，不能运行中丢字段。
- 验收：identity、普通改名、双规则、handler异常、多个字段、输入映射不改；test_normalization.py／test_schema.py。已有目标键覆盖政策另行保留，不偷偷改为强制报错。

## 03．字段别名与类型转换的可选组合顺序（增强）

- 来源：[官方 #607](https://github.com/pyeve/cerberus/issues/607)。当前先rename再coerce，f='123'按f规则改g后仍是字符串；现有替代是在目标g上配置转换规则。
- 交付：显式输入别名／后置改名模式，使原字段的转换在发布新名称前完成；区分输入与输出schema的规则归属，旧模式不变。
- 验收：g为整数、目标已有独立规则、嵌套、重复目标、转换失败、最终验证路径；validator.py／schema.py，test_normalization.py／test_validation.py。不把新的处理顺序混作第02步数据丢失修复。

## 04．nullable字段的显式空值转换政策（增强）

- 来源：[官方 #427](https://github.com/pyeve/cerberus/issues/427)。原版str(None)得到'None'，int(None)失败后因nullable保留None；当前是实际处理约定，不强定为bug。
- 交付：可选skip_none/coerce_none政策，对转换链各阶段统一，保留当前默认行为；允许用户继续自写coercer。
- 验收：str/int/多段链、初始None、前一转换生成None、nullable=False、真实转换异常；validator.py，test_normalization.py。ignore_none_values原语义不被替换。

## 05．JSON可表达的受控coercer注册（增强）

- 来源：[官方 #316](https://github.com/pyeve/cerberus/issues/316)。coerce:'int'原版SchemaError，命名coercer目前需子类定义_normalize_coerce_*，不是完全不支持名字。
- 交付：显式实例注册表及可选标准转换器集，供纯数据schema引用；不根据字符串任意import/eval，不修改全局类注册。
- 验收：已注册／未知名称、同名实例隔离、链式转换、bool的明确文本政策、转换异常；schema.py／validator.py，test_customization.py／test_normalization.py。callable和旧子类扩展保留。

## 06．缺失字段的条件必填（增强）

- 来源：[官方 #622](https://github.com/pyeve/cerberus/issues/622)。dependencies只在被约束字段存在时检查；kind='choice'且缺value原版可通过，属于现有语义。
- 交付：required_if按兄弟／根字段条件决定缺失字段是否必填，缺失、None、False与默认值的阶段顺序明确。
- 验收：条件成立／不成立、字段缺失／None、嵌套、update=True政策、purge/default组合；validator.py／schema.py，test_validation.py。原dependencies不反转含义，可继续用自定义检查实现。

## 07．字段之间的声明式比较约束（增强）

- 来源：起止日期、最小／最大业务值需相互比较。当前min/max是固定值，dependencies检查存在与允许值；可自写check_with读取self.document。
- 交付：compare_to以受控操作符和字段引用表达比较，支持缺失政策，不eval表达式；格式转换后再比较。
- 验收：start≤end、相等、目标不存在、不可比较类型、嵌套／根引用、转换错误；validator.py／schema.py，test_validation.py。错误定位约束字段并带引用位置，不把类型错误静默当通过。

## 08．default_setter获得字段与路径上下文（增强）

- 来源：[官方 #279](https://github.com/pyeve/cerberus/issues/279)。当前setter只收mapping；要按当前字段名查用户允许值需要多闭包或外部状态。
- 交付：独立context-aware setter协议，提供字段、文档路径和只读配置；旧setter(mapping)继续适用，不能通过吞TypeError猜模式。
- 验收：同setter不同字段、嵌套、依赖顺序、循环依赖、setter自身异常、并发独立实例；validator.py，test_normalization.py／test_customization.py。传入业务上下文由应用显式提供。

## 09．每次校验产生独立结果对象（增强）

- 来源：Validator把document/errors保存在可变实例上；validated已能返回文档，但没有同时携带规范化结果、错误和完成状态的原生validate_result。
- 交付：不可变结果外壳及明确文档快照政策，包含成功状态与本次错误；后续调用不覆盖上一结果，不让同一Validator突然被宣传为线程安全。
- 验收：成功／失败连续调用、always_return_document对照、嵌套可变值的选定隔离政策、自定义handler；validator.py／errors.py，test_validation.py／test_errors.py。保留现有bool/None返回接口。

## 10．可移植的机器可读错误记录（增强）

- 来源：BasicErrorHandler输出嵌套消息，已有ErrorList/DocumentErrorTree可定制；缺少稳定JSON记录与无歧义路径编码的公开导出契约。
- 交付：iter_error_records输出规则标识、文档／schema路径与原因，值是否包含由显式选项决定；复合错误保留父子关系，支持JSON Pointer转义。
- 验收：列表索引、字段含点／斜线／波浪线、非字符串键的明确编码、逻辑错误树、自定义错误；errors.py，test_errors.py。不能宣称目前完全没有结构化错误，也不只换一个方法名。

## 11．校验工作量与错误数量预算（增强）

- 来源：大文档和复合schema可能累计大量错误。原版传max_errors=1仍出现2个字段错误，因为它不是已支持选项。
- 交付：显式预算限制节点／深度／规则调用／叶子错误数量，并报告未完成；逻辑验证不能因预算中止误判成功。
- 验收：正好到界、错误上限、深层映射、anyof部分求值、用户check异常、未设预算的完整原行为；validator.py／errors.py，test_validation.py／test_errors.py。不承诺中断不返回的用户callable。

## 12．逐条验证数据流（增强）

- 来源：批量JSON记录当前需用户循环validate并及时复制实例状态，没有iter_validated等有明确错误政策的批接口。
- 交付：惰性逐条结果，保留输入序号，支持遇错停止／继续；不把整条输入流实体化，不跨记录共享默认可变状态。
- 验收：首条可提前取得、空流、坏记录之后恢复、一次性输入、消费者close、预算；validator.py及新增批接口，test_assorted.py／test_validation.py。可以内部独立结果实现，不强造对第09步的开发顺序依赖。

## 13．可移植schema与注册表包（增强）

- 来源：schema/rules注册表已存在，但跨进程导出完整引用集、版本和可验证配置需要应用自行实现；含callable的schema并非自然JSON可保存。
- 交付：版本化SchemaBundle，收集引用及声明的扩展名，导入前校验；不可移植callable明确报错或要求应用注册，绝不隐式pickle。
- 验收：递归引用、缺失引用、重复名字、未知版本、导入失败不污染原注册表、简单JSON往返；schema.py／utils.py，test_registries.py／test_schema.py。首版可只支持无callable子集，不依赖第05步。

## 14．schema语义诊断（增强）

- 来源：min=10/max=0的schema原版可构造，类型结构验证不等于语义可满足检查；无lint_schema入口。
- 交付：独立诊断通道检查矛盾边界、无法满足的必填／排斥组合、坏regex与可判定的引用问题，默认不改变现有准入。
- 验收：确定矛盾、可能合法的复杂分支不误拒绝、警告路径、regex编译错误、循环引用、未知自定义规则；schema.py，test_schema.py／test_registries.py。不声称能判定任意Python规则的可满足性。

## 15．明示能力损失的JSON Schema导出（增强）

- 来源：[官方比较议题 #254](https://github.com/pyeve/cerberus/issues/254)及跨工具消费场景；当前没有to_json_schema，不能直接把Cerberus规则字典当标准JSON Schema。
- 交付：固定目标草案、有限可映射验证子集；归一化／任意callable等不可映射项必须诊断或拒绝，不静默删除后称等价。
- 验收：类型／范围／必填／嵌套的正反样例用独立validator对照，unsupported规则清单、nullable与unknown政策；新增转换模块，test_schema.py及新互操作测试。不执行本轮尚未写出的导出器并声称已通过。

## 16．按字段名模式选择schema（增强）

- 来源：动态指标键需要不同值约束。keysrules验证键本身，allow_unknown可给所有未知键同一规则，两者不等价于按名称分派值schema。
- 交付：pattern_fields，明确精确字段优先级、多模式命中合并／拒绝、无匹配时unknown政策；规则预检查，保留keysrules独立语义。
- 验收：多种前缀、多个命中、坏模式、含特殊字符的键、嵌套、purge_unknown组合；validator.py／schema.py，test_validation.py。不承诺标准re引擎具有强制执行超时。

## 17．数值有限性约束（增强）

- 来源：JSON／金额数据不接受NaN/Infinity。原版number配min/max对NaN可通过，类型判断与Python比较语义不直接等价于有限数约束，按增强处理。
- 交付：显式finite规则，分别定义float与注册Decimal类型的非有限值；保留未声明finite的当前行为，不把现有number已排除bool再算新能力。
- 验收：NaN、±Infinity、普通数、0、Decimal有限／非有限、非数字类型错误；validator.py／schema.py，test_validation.py／test_customization.py。一个数值域政策，不拆多个特殊值计步。

## 18．有界的归一化解释记录（增强）

- 来源：输出字段经rename/default/coerce/purge多阶段改变，当前只有最终document与错误，不能直接解释某值为何变化。
- 交付：opt-in trace记录阶段、路径、动作和可选前后值，限制条数并支持脱敏；默认不保存敏感内容或调用对象引用。
- 验收：改名／默认／转换／清除、转换失败、嵌套、trace上限、自定义coercer、启用前后结果一致；validator.py／errors.py，test_normalization.py／test_errors.py。与第09步一次最终结果不同，逐阶段记录不另算多步。

## 19．用户转换器的输入容器隔离（增强）

- 来源：normalized目前浅复制初始映射，用户coercer若append到列表，原输入同样变化；本轮实际观察items从[1]变[1,2]。不把用户callable的副作用当既有库bug。
- 交付：opt-in isolate_input，对支持的JSON式容器复制后再传转换器；不支持的对象有明确拒绝／自定义clone政策，默认行为保留。
- 验收：嵌套共享列表、失败转换、环／深度预算、自定义类型、输入不变且结果正确；validator.py／utils.py，test_normalization.py。只隔离传入容器，不声称撤销文件／数据库等外部副作用。

## 20．JSON/JSONL文件校验CLI（增强）

- 来源：原版无cerberus.__main__，当前要写Python脚本处理schema和记录文件。
- 交付：原生CLI读取纯数据schema及JSON/JSONL，输出正常化记录和独立错误流，区分配置错／数据错退出码；不eval schema或默认加载任意Python插件。
- 验收：中文与类型转换、非法schema、坏行、输入输出冲突、stdin流、输出失败、无大批物化；新增__main__.py／CLI测试并回归全套。初版支持现有无callable规则即可，命名coercer可作为后续组合，不强依赖第05步。

## 验收边界

原版基线与缺口研究已经运行，上述改进尚未实施。后续冻结验收须加载候选Cerberus，观测校验结果、原始输入、错误路径和实际文件输出；保留原生用例并累计先前能力。平台原生入口与预算适配仍需独立完成。
