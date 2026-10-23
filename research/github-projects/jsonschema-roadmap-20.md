# jsonschema：二十步真实工程迭代路线

固定 [python-jsonschema/jsonschema@c497561ea0a95f5aac09cd63d15eb1420eb7bbec](https://github.com/python-jsonschema/jsonschema/tree/c497561ea0a95f5aac09cd63d15eb1420eb7bbec)，原生证据见 [单仓审查](./jsonschema.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．2019-09布尔items与未评估项兼容

- **类型与来源**：修复；[官方 #1590](https://github.com/python-jsonschema/jsonschema/issues/1590) 与固定源码。
- **原版现状与收益**：items=true时旧草案辅助函数对bool调用len，实测抛TypeError。
- **交付及模块**：按布尔schema含义计算已评估项，保留unevaluatedItems正确范围；_legacy_keywords.py:find_evaluated_item_indexes_by_schema／unevaluatedItems。
- **兼容与依赖**：只修旧草案items语义，不把2020-12 prefixItems规则套到2019-09；步骤依赖：无。
- **正常验收**：items=true的空／非空数组无错误，false按各自标准产生ValidationError。
- **异常／边界验收**：tuple items、additionalItems、contains、组合分支不丢评估信息。
- **原生回归**：jsonschema/tests/test_validators.py、test_jsonschema_test_suite.py。

## 02．错误JSONPath精确定位含换行键

- **类型与来源**：修复；[官方 #1589](https://github.com/python-jsonschema/jsonschema/issues/1589) 与固定源码。
- **原版现状与收益**：属性x
渲染为$.x
，jsonpath-ng实际取x而非x
。
- **交付及模块**：判断dot-safe键使用完整字符串匹配，其余使用正确引用和转义；exceptions.py:_Error.json_path。
- **兼容与依赖**：普通identifier输出保持；path仍是原始str/int序列，不修改实例键；步骤依赖：无。
- **正常验收**：x与x
同时存在时JSONPath只取真正错误值1。
- **异常／边界验收**：引号、反斜杠、空键、Unicode、回车、数组索引混合路径都可往返。
- **原生回归**：jsonschema/tests/test_exceptions.py、jsonpath-ng独立选择对照。

## 03．一次性错误上下文父链完整

- **类型与来源**：修复；[官方 #1584](https://github.com/python-jsonschema/jsonschema/issues/1584) 与固定源码。
- **原版现状与收益**：context=list(iterator)后第二次迭代原context，子错误无parent，绝对路径缺record。
- **交付及模块**：只固定一次context，给固定后的每个子错误挂parent；exceptions.py:_Error.__init__、SchemaError／ValidationError。
- **兼容与依赖**：list/tuple既有行为保持；子对象身份不被复制，祖先环路不引入；步骤依赖：无。
- **正常验收**：generator/list/tuple的子绝对实例／schema路径相等。
- **异常／边界验收**：空context、深层嵌套、SchemaError转换与一个iterator禁止二次消费。
- **原生回归**：jsonschema/tests/test_exceptions.py。

## 04．正则格式非法输入稳定转为校验错误

- **类型与来源**：修复；[官方 #1558](https://github.com/python-jsonschema/jsonschema/issues/1558) 与固定源码、#1538。
- **原版现状与收益**：FormatChecker只捕获re.error，冲突flags ValueError和深度RecursionError实测漏出。
- **交付及模块**：把受控编译失败映射FormatError，包含必要的ValueError／RecursionError／OverflowError族；_format.py:is_regex、FormatChecker登记异常。
- **兼容与依赖**：不捕获任意BaseException或KeyboardInterrupt；一般custom checker的编程错误仍传播；步骤依赖：无。
- **正常验收**：正常正则通过、两组冲突flags及深嵌套均返回格式错误。
- **异常／边界验收**：空字符串、bytes非字符串、超大repeat和原re.error分支，异常cause保留。
- **原生回归**：jsonschema/tests/test_format.py。

## 05．duration指数溢出受控报告

- **类型与来源**：修复；[官方 #1511](https://github.com/python-jsonschema/jsonschema/issues/1511) 与固定源码。
- **原版现状与收益**：isoduration对P1E1000000D抛decimal.Overflow，原版验证中断。
- **交付及模块**：受控数值解析失败转为duration格式错误，限定输入资源边界；_format.py:is_duration。
- **兼容与依赖**：可选依赖缺失的既有行为保持；不把未知依赖错误统统当用户格式错误；步骤依赖：无。
- **正常验收**：常用ISO duration通过，大指数失败为ValidationError。
- **异常／边界验收**：符号、nan样文本、负值策略按当前格式语法，原cause和无dep分支可观察。
- **原生回归**：jsonschema/tests/test_format.py。

## 06．2020-12相对JSON Pointer草案选择

- **类型与来源**：修复；[官方 #1533](https://github.com/python-jsonschema/jsonschema/issues/1533) 与固定源码。
- **原版现状与收益**：当前2020-12复用旧解析器，0+1/foo实测被拒。
- **交付及模块**：草案分别注册正确的相对指针解析器，支持该草案index manipulation；_format.py:is_relative_json_pointer及draft登记。
- **兼容与依赖**：Draft7／2019-09继续旧语法；不跨草案放宽；步骤依赖：无。
- **正常验收**：2020-12接受合法0+1/foo／1-2/bar，旧草案拒绝。
- **异常／边界验收**：前导零、空后缀、负数越界语法、#形式和非字符串保持标准边界。
- **原生回归**：jsonschema/tests/test_format.py、test_jsonschema_test_suite.py。

## 07．格式字符串拒绝额外尾换行

- **类型与来源**：修复；[官方 #1588](https://github.com/python-jsonschema/jsonschema/issues/1588) 与固定源码。
- **原版现状与收益**：date-time／uri／uri-reference／hostname实测接受单个末尾LF，time对照拒绝。
- **交付及模块**：对严格字符语法保证完整输入验证，修正本库和可选依赖适配边界；_format.py及相关格式器包装。
- **兼容与依赖**：不全局strip输入，也不能禁止本来允许换行的其他格式；每格式按规范；步骤依赖：无。
- **正常验收**：正常URL／hostname／时间通过，追加LF／CRLF应按各格式拒绝。
- **异常／边界验收**：内嵌控制字符、末空格、非字符串、可选依赖不同分支及time通过对照。
- **原生回归**：jsonschema/tests/test_format.py、test_jsonschema_test_suite.py。

## 08．已评估元素查询线性化

- **类型与来源**：性能增强；[官方 #1536](https://github.com/python-jsonschema/jsonschema/issues/1536) 与固定源码。
- **原版现状与收益**：辅助函数生成list后对每元素做线性membership，大宽数组／对象可能二次增长，源码已确认但本轮未做性能承诺。
- **交付及模块**：保持注释语义的索引／键集合，减少重复membership扫描；_utils.py、_legacy_keywords.py、_keywords.py:unevaluatedItems/Properties。
- **兼容与依赖**：保留if/then/else、anyOf、ref和contains正确的成功分支评估；小实例开销须记录；步骤依赖：无。
- **正常验收**：基准在相同固定环境比较200/400/800/1600宽度，结果集合完全相同。
- **异常／边界验收**：复杂schema不误标失败分支为已评估，内存额外成本有预算；不只断言墙钟阈值。
- **原生回归**：jsonschema/tests/test_utils.py、test_validators.py、原生benchmarks适用集合。

## 09．错误的结构化原因细节

- **类型与来源**：增强；[官方 #119](https://github.com/python-jsonschema/jsonschema/issues/119) 与固定源码、#992、#993、#1363。
- **原版现状与收益**：required等错误需要从message反解析字段名，minContains计数／uniqueItems重复索引不完整暴露。
- **交付及模块**：增加稳定reason_code及details，涵盖缺字段、额外键、匹配数量和重复项位置；exceptions.py:_Error、_keywords.py及旧草案关键字。
- **兼容与依赖**：message和现有path不变；details默认不放实例值，多个相关元数据族一次交付；步骤依赖：无。
- **正常验收**：调用方直接取missing_property／unexpected_properties／match_count等。
- **异常／边界验收**：键名含引号、多个缺失、复杂相等的重复数组项和schema错误，序列化有界。
- **原生回归**：jsonschema/tests/test_exceptions.py、test_validators.py。

## 10．错误消息翻译渲染接口

- **类型与来源**：增强；[官方 #971](https://github.com/python-jsonschema/jsonschema/issues/971) 与固定源码。
- **原版现状与收益**：消息为关键字函数硬编码文本，调用者要重写逻辑提取细节才能翻译。
- **交付及模块**：基于reason_code/details提供独立render_error(locale/catalog)扩展钩子；exceptions.py、格式渲染helper。
- **兼容与依赖**：核心校验语义和默认English message保持；不设置全局gettext域；步骤依赖：09。
- **正常验收**：同一个ValidationError渲染为不同目录语言，不重跑验证。
- **异常／边界验收**：缺翻译回退、复数、嵌套context、custom keyword和安全消息模式不泄漏值。
- **原生回归**：jsonschema/tests/test_exceptions.py、test_validators.py。

## 11．一次抛出全部验证异常

- **类型与来源**：增强；[官方 #1011](https://github.com/python-jsonschema/jsonschema/issues/1011) 与固定源码。
- **原版现状与收益**：validate只抛首错，iter_errors返回流；没有公开ExceptionGroup入口。
- **交付及模块**：增加validate_all或等价命名收集独立错误并抛ExceptionGroup，可配明确错误上限；validators.py:create生成的方法、协议声明。
- **兼容与依赖**：validate/is_valid/iter_errors保持；Python≥3.12已有原生ExceptionGroup；步骤依赖：无。
- **正常验收**：两个不相关字段错误在同一组且可except* ValidationError。
- **异常／边界验收**：无错不抛、schema错误不混为instance错误、达到上限标截断，不把无限错误源全部读入。
- **原生回归**：jsonschema/tests/test_validators.py、typing适用协议用例。

## 12．组合内建与业务格式检查

- **类型与来源**：增强；[官方 #1496](https://github.com/python-jsonschema/jsonschema/issues/1496) 与固定源码。
- **原版现状与收益**：FormatChecker.checks同名覆盖旧checker，无法声明all/any组合。
- **交付及模块**：提供compose(format,mode,checker)或克隆注册入口，保留内建cause和自定义诊断；_format.py:FormatChecker。
- **兼容与依赖**：原checks覆盖语义保持，组合显式；不全局改其他实例；步骤依赖：无。
- **正常验收**：日期格式先通过内建语法，再通过业务年份限制。
- **异常／边界验收**：all/any短路、不同raises、空组合拒绝、checker抛编程错误不静默吞掉。
- **原生回归**：jsonschema/tests/test_format.py。

## 13．无$id的schema显式基准URI

- **类型与来源**：增强；[官方 #1547](https://github.com/python-jsonschema/jsonschema/issues/1547) 与固定源码、#1454。
- **原版现状与收益**：构造器可registry但无公开base_uri；CLI有旧resolver --base-uri不能替代新Registry API。
- **交付及模块**：支持公开base_uri／retrieval_uri配置，交给referencing root resolver，避免用户改私有_resolver；validators.py:create／__attrs_post_init__、协议。
- **兼容与依赖**：schema显式$id的优先级明确，现有registry仍可用；禁止隐式联网；步骤依赖：无。
- **正常验收**：本地内存相对ref多层按给定base正确解析。
- **异常／边界验收**：schema有$id、空base、相对base拒绝、URI fragment和动态ref作用域回归。
- **原生回归**：jsonschema/tests/test_validators.py、test_cli.py。

## 14．可注入正则执行后端

- **类型与来源**：增强；[官方 #1142](https://github.com/python-jsonschema/jsonschema/issues/1142) 与固定源码。
- **原版现状与收益**：pattern/patternProperties与regex格式使用Python re，官方ECMA用例有明确跳过。
- **交付及模块**：提供受控regex backend协议，默认re，显式选择更符合ECMA的后端；_keywords.py、_format.py、validators.py构造／evolve。
- **兼容与依赖**：不声称Python re能覆盖ECMA；可选后端额外依赖单独准备和计费；步骤依赖：无。
- **正常验收**：同backend作用于pattern与patternProperties，支持所声明的Unicode property。
- **异常／边界验收**：无后端依赖给明确配置错，编译失败／超时策略、evolve/ref继承一致。
- **原生回归**：jsonschema/tests/test_validators.py、test_format.py、test_jsonschema_test_suite.py。

## 15．schema关键字使用诊断

- **类型与来源**：增强；[官方 #778](https://github.com/python-jsonschema/jsonschema/issues/778) 与固定源码。
- **原版现状与收益**：check_schema对propeties拼写实测接受；不同draft新增关键字也可能被静默当annotation。
- **交付及模块**：增加独立lint_schema报告疑似拼写／草案不支持的已知关键字，不改变验证标准；validators.py、独立schema诊断helper。
- **兼容与依赖**：JSON Schema允许扩展keyword，默认不拒绝；custom vocabulary白名单明确；步骤依赖：无。
- **正常验收**：draft4使用const给有位置诊断，正确properties无警告。
- **异常／边界验收**：未知自定义关键字可白名单、$defs内嵌套、切换$schema按局部draft判断。
- **原生回归**：jsonschema/tests/test_validators.py、test_jsonschema_test_suite.py。

## 16．保证不含实例值的诊断

- **类型与来源**：增强；[官方 #1218](https://github.com/python-jsonschema/jsonschema/issues/1218) 与固定源码、#1271。
- **原版现状与收益**：error.message和__str__可带输入／schema，原版无safe_message。
- **交付及模块**：提供safe_reason与受控renderer，按开关隐藏实例和无关注释关键字；exceptions.py、渲染helper。
- **兼容与依赖**：旧message不变；不能仅删repr(instance)再称无泄漏，使用结构化安全模板；步骤依赖：09。
- **正常验收**：合成secret出现在enum/type/pattern等失败中时safe输出不含secret。
- **异常／边界验收**：嵌套context、schema自带secret、超长值与custom keyword无安全模板时回退代码／路径。
- **原生回归**：jsonschema/tests/test_exceptions.py、test_validators.py。

## 17．已弃用字段的独立警告流

- **类型与来源**：增强；[官方 #1170](https://github.com/python-jsonschema/jsonschema/issues/1170) 与固定源码。
- **原版现状与收益**：deprecated是annotation，不参与现有instance有效性；无内建告警遍历。
- **交付及模块**：新增opt-in注释诊断收集deprecated的实际实例位置，返回warning而非默认ValidationError；validators.py、annotation helper。
- **兼容与依赖**：不把标准annotation强行变错误；默认validate有效性完全保持；步骤依赖：无。
- **正常验收**：只在实例实际存在已弃用字段时给对应路径warning。
- **异常／边界验收**：if/oneOf/ref评估分支、数组和缺字段不产生误告，重复引用诊断去重。
- **原生回归**：jsonschema/tests/test_validators.py、test_jsonschema_test_suite.py。

## 18．引用解析路径可诊断

- **类型与来源**：增强；[官方 #1146](https://github.com/python-jsonschema/jsonschema/issues/1146) 与固定源码。
- **原版现状与收益**：旧resolver._scopes_stack已废弃，新错误没有公开ref链。
- **交付及模块**：提供opt-in resolution trace，仅记录URI／schema路径与结果，附着验证报告或事件回调；validators.py:descend／$ref适配、referencing集成。
- **兼容与依赖**：默认无额外跟踪开销，不访问私有resolver栈或发额外请求；步骤依赖：无。
- **正常验收**：root→defs→resource本地引用失败可解释经过的URI链。
- **异常／边界验收**：循环／动态ref、同资源多路径、未解析URI、诊断数量有界且不含实例值。
- **原生回归**：jsonschema/tests/test_validators.py、test_exceptions.py。

## 19．只需首错时限制组合上下文收集

- **类型与来源**：增强；[官方 #517](https://github.com/python-jsonschema/jsonschema/issues/517) 与固定源码。
- **原版现状与收益**：is_valid虽短路，但anyOf/oneOf首个错误先物化所有子错误context，昂贵分支不能被真正省略。
- **交付及模块**：提供显式error_detail=basic/lazy/full策略，basic在可证明失败时不构造完整context；_keywords.py:anyOf／oneOf、exceptions.py:context、validators.py。
- **兼容与依赖**：默认full保持；不得为少收错误改变oneOf恰好一个成功的语义；步骤依赖：无。
- **正常验收**：基本模式的valid结论与完整模式一致，而受控计数证明少构造错误对象。
- **异常／边界验收**：空分支、两个成功oneOf、deep refs、generator关闭和用户后续请求细节的契约清楚。
- **原生回归**：jsonschema/tests/test_validators.py、test_exceptions.py。

## 20．扩展对象类型的统一访问适配

- **类型与来源**：增强；[官方 #727](https://github.com/python-jsonschema/jsonschema/issues/727) 与固定源码。
- **原版现状与收益**：TypeChecker可判namedtuple为object，但required/additionalProperties仍直接用in／keys，类型扩展不完整。
- **交付及模块**：提供对象访问协议get/keys/contains adapter，供全部object相关keyword一致调用；_types.py、_keywords.py、_legacy_keywords.py、validators.py。
- **兼容与依赖**：dict默认路径保持快速；用户显式类型adapter才参与，不全局把所有iterable看作object；步骤依赖：无。
- **正常验收**：namedtuple或只读Mapping的properties／required／additionalProperties结果一致。
- **异常／边界验收**：访问器错误、non-string键、patternProperties、dependentRequired、unevaluatedProperties统一且不修改实例。
- **原生回归**：jsonschema/tests/test_types.py、test_validators.py、test_jsonschema_test_suite.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
