# pyparsing：二十步真实工程迭代路线

固定 [pyparsing/pyparsing@810199f89bf916590426e1c5cb3d612584f11a2f](https://github.com/pyparsing/pyparsing/tree/810199f89bf916590426e1c5cb3d612584f11a2f)，原生证据见 [单仓审查](./pyparsing.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．语法结构静态检查

- **来源／场景**：复杂配置语法在运行前发现空匹配重复、未赋值Forward等问题；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：已有validate及运行警告，但没有统一lint_grammar报告语法图风险与位置
- **交付及模块**：提供只读语法检查器，报告未定义引用、空消费重复、不可达分支和明显遮蔽；`pyparsing/core.py:ParserElement`。
- **兼容与实际依赖**：不执行parse action；只对可证明的规则报确定问题，动态动作标未知；现有validate保持；步骤依赖：无。
- **正常验收**：空消费表达式置于重复内、未赋值Forward得到具体节点报告
- **异常／边界验收**：共享节点、循环引用、用户Token子类及复杂条件不误判为必然错误
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 02．受支持的EBNF互换

- **来源／场景**：文档已有EBNF，维护者希望转换到可调用语法并反向导出；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：examples/ebnf.py有示例解析器，包无load_ebnf/导出合同；create_diagram是铁路图非EBNF
- **交付及模块**：把示例可支持子集整理为稳定导入/导出模块，声明语义范围并提供自定义终结符表；`pyparsing/core.py:ParserElement`, `examples/ebnf.py:parse`。
- **兼容与实际依赖**：承认示例已存在，交付是公开化与互换合同；parse action等Python语义不可伪装无损导出；步骤依赖：无。
- **正常验收**：规定EBNF子集导入后解析相同样本，导出再导入保持识别结果
- **异常／边界验收**：未定义符号、重复定义、递归、特殊序列和动作节点有明确拒绝/外部引用声明
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 03．编辑器期待项补全

- **来源／场景**：配置编辑器在光标处提示合法关键字；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：ParseException描述单次失败，scan_string用于匹配，无complete_at期待项集合
- **交付及模块**：新增不执行业务动作的前缀分析，返回可达终结符、替换范围和上下文；`pyparsing/core.py:ParserElement`, `pyparsing/exceptions.py:ParseBaseException`。
- **兼容与实际依赖**：不把每个字符串前缀当完整parse成功；补全不执行用户动作，不修改语法；步骤依赖：无。
- **正常验收**：枚举关键字与等号后的数值类别在正确位置建议
- **异常／边界验收**：嵌套选择、空匹配、注释、引号未闭合和递归预算有稳定退出，不无限列举字串
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 04．可恢复的批次解析

- **来源／场景**：多行业务配置希望同时报告几行错误并保留其余有效项；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：parse_string首次失败即异常；可自行按行循环但多行记录没有统一同步边界
- **交付及模块**：新增parse_recovering，调用方声明记录及同步点，返回结果和有序错误集合；`pyparsing/core.py:ParserElement.parse_string`, `pyparsing/exceptions.py`。
- **兼容与实际依赖**：默认严格解析不变；恢复动作不是默默接受无效字段；已执行动作的可回滚性明确；步骤依赖：无。
- **正常验收**：三条记录中一条坏记录时保留两条有效项及准确错误
- **异常／边界验收**：同步点出现在引号/注释内、多行记录、连续坏记录和EOF不丢失未消费范围
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 05．局部编辑后的增量重解析

- **来源／场景**：本地编辑器修改一个配置值希望复用未受影响结果；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：packrat缓存每次parse_string重置，无跨编辑reparse_edit合同
- **交付及模块**：新增显式增量会话，记录输入版本、节点依赖范围和编辑失效规则；`pyparsing/core.py:ParserElement.parse_string`, `pyparsing/core.py:ParserElement.reset_cache`。
- **兼容与实际依赖**：只复用声明纯动作且未受影响的节点；默认parse_string保持；不把旧loc当新位置；步骤依赖：无。
- **正常验收**：中间单值编辑后结果与整串重解析一致，未受影响片段可证明复用
- **异常／边界验收**：插入/删除改变位置、跨行注释、动作依赖上下文和语法变更必须正确扩大失效或全量回退
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 06．分块扫描文本

- **来源／场景**：长文本提取整数或记录需要边读取边产出；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：scan_string需要完整str，parse_file读取整份文件；无scan_chunks生命周期
- **交付及模块**：新增分块扫描器，说明最大跨块匹配窗口、EOF及重叠结果规则；`pyparsing/core.py:ParserElement.scan_string`, `pyparsing/core.py:ParserElement.parse_file`。
- **兼容与实际依赖**：现有scan_string坐标不变；无法界定匹配长度的语法要求显式缓冲预算/拒绝；步骤依赖：无。
- **正常验收**：任意分块的有限长记录扫描与整串结果及绝对位置一致
- **异常／边界验收**：跨块引号、注释、Unicode、重叠匹配和尾块不足不能重复/漏报
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 07．明确编码的字节解析

- **来源／场景**：文件导入需要把错误位置映射回原始字节；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：parse_string合同为str；parse_file有encoding但无字节位置结果及parse_bytes
- **交付及模块**：提供parse_bytes，显式codec解码并可返回字符到原始字节位置映射；`pyparsing/core.py:ParserElement.parse_file`, `pyparsing/exceptions.py:ParseBaseException`。
- **兼容与实际依赖**：不猜编码；不是二进制协议解析器；原str入口保持；步骤依赖：无。
- **正常验收**：UTF8中文文本解析结果正确，错误字符loc能映射对应字节偏移
- **异常／边界验收**：BOM、多字节、错误解码、CRLF和tab扩展的坐标口径明确，不把字符序号当字节数
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 08．按字素匹配的词元素

- **来源／场景**：自然语言短语包含组合字符和emoji，字符数限制应按可见字素；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：Word/CharsNotIn按Python码点工作，unicode集合解决脚本字符集但不提供GraphemeWord
- **交付及模块**：新增可选字素词元素，明确Unicode分段版本、允许类别与min/max计量；`pyparsing/core.py:Word`, `pyparsing/unicode.py`。
- **兼容与实际依赖**：旧Word含义不变；字素规则可能需要独立可选依赖，提前冻结并记录成本；步骤依赖：无。
- **正常验收**：组合é与预组合é按一个字素计量，emoji序列不被中途切断
- **异常／边界验收**：区域旗帜、ZWJ、孤立组合字符、控制字符和空匹配行为有精确断言
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 09．区域化Decimal语法助手

- **来源／场景**：本地表单使用德文1.234,50或法文不换行空格分组；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/common.py)。
- **原版缺口**：common已有integer/real/number，面向固定数字记法，无localized_decimal合同
- **交付及模块**：新增明确locale/分组/精度规则的Decimal解析器，可通过可选Babel数据适配；`pyparsing/common.py:pyparsing_common`, `pyparsing/core.py:ParserElement`。
- **兼容与实际依赖**：不改变已有number返回类型；不用float冒充高精度；locale不由宿主自动决定；步骤依赖：无。
- **正常验收**：明确de_DE规则将1.234,50解析为Decimal1234.50，严格分组校验
- **异常／边界验收**：非法分组、负号、空格变体、科学表示与歧义小数点按选项拒绝或解释
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 10．单次解析配置上下文

- **来源／场景**：两个独立语法需要不同空白、缓存与递归策略；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：enable_packrat/enable_left_recursion和缓存是ParserElement类级状态；testing有重置工具但无生产ParsingContext
- **交付及模块**：提供隔离解析上下文，承载配置/缓存/诊断并明确线程与嵌套归属；`pyparsing/core.py:ParserElement.enable_packrat`, `pyparsing/core.py:ParserElement.enable_left_recursion`, `pyparsing/testing.py`。
- **兼容与实际依赖**：不承诺现有不兼容的packrat和左递归同时启用；原全局API兼容默认上下文；步骤依赖：无。
- **正常验收**：两个上下文分别启用不同模式交错解析，各自结果与独立运行一致
- **异常／边界验收**：嵌套上下文、异常退出、并发访问和不兼容选项不会改变兄弟配置
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 11．语法冻结快照

- **来源／场景**：可复用语法构建完后需避免运行中被意外set_parse_action等改动；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：ParserElement可变且copy不等于深度冻结，没有freeze合同
- **交付及模块**：新增可检查的冻结语法快照，递归冻结节点/动作列表，保留有意clone再编辑入口；`pyparsing/core.py:ParserElement`。
- **兼容与实际依赖**：默认构建方式不变；冻结是显式选择；不能冻结闭包内部状态并需声明此限制；步骤依赖：无。
- **正常验收**：冻结后修改方法及时拒绝，复制成可编辑新语法后原快照不变
- **异常／边界验收**：共享节点、Forward环、用户Token子类和动作外部可变值给明确边界
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 12．解析结果映射到数据类

- **来源／场景**：业务配置希望得到有类型的dataclass而非手写as_dict赋值；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/results.py)。
- **原版缺口**：ParseResults有as_list/as_dict，缺少to_dataclass及字段错误定位
- **交付及模块**：提供独立显式映射器，支持命名结果、可选字段、嵌套数据类和转换错误；`pyparsing/results.py:ParseResults.as_dict`。
- **兼容与实际依赖**：不改变ParseResults的字典/列表双重语义；默认不执行任意类型构造副作用；步骤依赖：无。
- **正常验收**：命名字段和嵌套Group可转到声明数据类，int值保持类型
- **异常／边界验收**：缺必填、多余字段、重复结果名、列表与标量冲突均定位映射路径
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 13．自动采集词元来源

- **来源／场景**：业务编辑器想让所有输出字段关联原文位置；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：Located可手动包每个表达式，是已有替代；无全语法自动provenance采集
- **交付及模块**：新增可选全局采集模式，记录输出词元对应表达式与原字符范围；`pyparsing/core.py:Located`, `pyparsing/results.py:ParseResults`。
- **兼容与实际依赖**：不把Located重新计作新能力；原返回结构不变，来源作为旁路映射；步骤依赖：无。
- **正常验收**：多个命名字段、Suppress标点和转换int后的值都有对应原文范围
- **异常／边界验收**：重复同值词元、合并/删除的parse action、tab扩展和零宽节点不错误一一对应
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 14．稳定机器诊断

- **来源／场景**：编辑器不能从英文异常字符串提取错误字段；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/exceptions.py)。
- **原版缺口**：ParseBaseException含loc/msg/parser_element且explain返回文字，无to_diagnostic合同
- **交付及模块**：增加版本化结构化错误，含范围、期待类目、语法节点与嵌套原因；`pyparsing/exceptions.py:ParseBaseException`, `pyparsing/core.py:ParserElement`。
- **兼容与实际依赖**：str(exc)/explain既有显示保持；不把未能枚举的自定义期待项猜成完整列表；步骤依赖：无。
- **正常验收**：未闭合引号与错误数字得到各自loc、错误码及合理提示类目
- **异常／边界验收**：EOF、多行、Unicode、ParseFatalException和用户动作异常的阶段区分清楚
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 15．语义动作的每次调用上下文

- **来源／场景**：同一解析器需不同变量表，闭包/全局字典不适合复用；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：set_parse_action签名适配s/loc/toks，用户可用闭包，但无parse_with_context
- **交付及模块**：增加显式不可变调用context，按声明提供给动作并纳入缓存归属；`pyparsing/core.py:ParserElement.set_parse_action`, `pyparsing/core.py:ParserElement.parse_string`。
- **兼容与实际依赖**：旧0-3参数动作继续；不得把不同context结果共用packrat缓存；步骤依赖：无。
- **正常验收**：同一语法分别用两张变量表求相同文本，结果各自正确
- **异常／边界验收**：嵌套解析、context缺键、动作抛错与并发调用不串用状态
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 16．可等待的本地语义动作

- **来源／场景**：异步应用需要在解析动作中等待已有本地协程能力；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：公开parse_string为同步；传async函数不等于得到已等待结果，无parse_async
- **交付及模块**：新增明确async解析入口，异步动作依序await，支持取消并保持语法选择语义；`pyparsing/core.py:ParserElement.set_parse_action`, `pyparsing/core.py:ParserElement.parse_string`。
- **兼容与实际依赖**：同步入口不偷偷运行事件循环；不增加网络需求；仅承诺显式async入口；步骤依赖：无。
- **正常验收**：一个本地异步转换动作被等待后返回最终ParseResults，执行顺序可观察
- **异常／边界验收**：取消、动作异常、嵌套循环与推测分支动作的副作用规则必须明确，不执行被回溯动作两次
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 17．语法节点性能报告

- **来源／场景**：维护复杂语法需找出回溯热点与缓存收益；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：set_debug_actions能手工观察，packrat有汇总统计，但无profile_parse的逐节点报告
- **交付及模块**：提供可选节点调用次数/失败次数/耗时/缓存命中报告，并保留递归图关系；`pyparsing/core.py:ParserElement.set_debug_actions`, `pyparsing/core.py:ParserElement.enable_packrat`。
- **兼容与实际依赖**：默认无性能采集开销；不以测量改变动作调用次数；计时器口径明确；步骤依赖：无。
- **正常验收**：有意重叠分支的语法报告显示热点，同输入结果与无profile一致
- **异常／边界验收**：共享节点、递归、命中缓存、异常退出和极短节点计时不出现负数或重复计总
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 18．注释与空白附属信息

- **来源／场景**：代码格式化工具希望修改字段时保留原注释与空白；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：ignore会跳过指定表达式，original_text_for保整段原文但无collect_trivia附着合同
- **交付及模块**：新增可选trivia采集，把跳过注释/空白按前后规则挂到语法节点；`pyparsing/core.py:ParserElement.ignore`, `pyparsing/helpers.py:original_text_for`。
- **兼容与实际依赖**：原默认忽略行为保持；与词元位置来源是不同交付，不能把注释当业务token污染原结果；步骤依赖：无。
- **正常验收**：行尾/行首注释被正确归属，可按原顺序重建未修改文本
- **异常／边界验收**：多行注释、文件首尾、仅注释输入、嵌套ignore和空白敏感语法有明确策略
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 19．按显示列渲染错误

- **来源／场景**：中文或emoji出现在出错点之前，终端插入符应对齐可见列；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/exceptions.py)。
- **原版缺口**：异常有字符loc及col，文字explain不提供可选Unicode显示宽度模式
- **交付及模块**：新增display_explain，保留机器字符坐标，单独计算终端显示列/截断窗口；`pyparsing/exceptions.py:ParseBaseException.explain`, `pyparsing/util.py:col`。
- **兼容与实际依赖**：默认异常格式保持；宽度依赖/Unicode版本明确，不把显示列代替字节或字符偏移；步骤依赖：无。
- **正常验收**：中文和组合字符行的caret在所选终端宽度规则下对齐出错位置
- **异常／边界验收**：tab、ZWJ、控制字符、超长行及窗口起点落在字素中间有明确可见转义
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。

## 20．有界候选解析

- **来源／场景**：有歧义文法需要给编辑器比较多个合法解释；[固定源码](https://github.com/pyparsing/pyparsing/blob/810199f89bf916590426e1c5cb3d612584f11a2f/pyparsing/core.py)。
- **原版缺口**：MatchFirst按顺序、Or按最长策略选择一个；不是全部解析枚举，无parse_candidates
- **交付及模块**：新增显式有界候选入口，限定支持的组合子和纯动作，返回不同解析及未穷尽状态；`pyparsing/core.py:MatchFirst`, `pyparsing/core.py:Or`, `pyparsing/core.py:ParserElement`。
- **兼容与实际依赖**：既有PEG选择语义不变；不宣称一般上下文无关文法完整枚举；必须有候选/工作上限；步骤依赖：无。
- **正常验收**：两个不同合法分支均可产生有来源的候选，重复等价结果可按策略去重
- **异常／边界验收**：递归、空分支、大组合爆炸、动作副作用和预算结束不伪称候选已穷尽
- **原生回归**：`tests/test_unit.py`, `tests/test_examples.py`, `tests/test_diagram.py`, `tests/test_simple_unit.py`, `tests/test_testing.py`, `tests/test_util.py`。
