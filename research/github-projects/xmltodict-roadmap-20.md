# xmltodict：二十步真实工程迭代路线

固定 [martinblech/xmltodict@6e29fba282e68631034dd2722a413b4e35276584](https://github.com/martinblech/xmltodict/tree/6e29fba282e68631034dd2722a413b4e35276584)，详见[单仓审查](./xmltodict.md)。共 20 步：20 项增强提案。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．可选完整 XML 1.0 名称校验（增强提案）

- 来源／场景：https://github.com/martinblech/xmltodict/issues/418
- 原版现状：现有 _validate_name 只防止标记上下文突破，空名和数字开头仍可能输出不可解析XML；上游明确这是已知宽松政策。
- 交付目标：提供 validate_names=xml10 的完整 Name/QName 规则，支持 Unicode 并报告元素／属性路径。
- 影响模块：xmltodict.py:_validate_name/_emit
- 兼容边界：默认现有最小校验保持；不把零散 ASCII 正则声称为完整 XML 语法，不放松现有注入防护。
- 正常验收：合法 Unicode、带命名空间的元素／属性可输出并被独立 XML 解析器接受。
- 异常／边界：空名、非法起始／组合字符、坏 QName、保留前缀分别明确拒绝，涵盖 XML1.0 范围。
- 原生回归：tests/test_dicttoxml.py 的 name validation/security 集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．可配置 XML 读取资源预算（增强提案）

- 来源／场景：[xmltodict.py:parse/_DictSAXHandler](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：Expat 有自身限制，但本库没有统一 max_input_bytes/max_depth/max_text/attrs 预算。
- 交付目标：提供 Limits 配置一次定义输入、嵌套、单节点文本、属性数上限，触发专用异常。
- 影响模块：xmltodict.py:parse 与 SAX 回调
- 兼容边界：默认不新增限制；预算不替代 disable_entities=True，也不宣称抵御全部恶意输入。
- 正常验收：在预算内读取订单相同，恰好到边界可用，超界及时终止。
- 异常／边界：UTF-8 多字节、跨 chunk、深节点、单节点大量属性及流式模式一致。
- 原生回归：tests/test_xmltodict.py 的 streaming/entities 集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．输入支持普通分块迭代器（增强提案）

- 来源／场景：[xmltodict.py:parse 中 isgenerator 分支](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：支持 generator 但 iter([bytes...]) 不是 generator；当前直接抛 TypeError，README仅承诺generator。
- 交付目标：泛化输入协议为明确的字节／文本 chunk Iterable，兼容列表迭代器与自定义迭代对象。
- 影响模块：xmltodict.py:parse
- 兼容边界：字符串／字节仍视为完整文档，不按字符迭代；文件对象优先 read。
- 正常验收：同一 XML 的 list_iterator、自定义 iterator 和 generator 解析结果一致。
- 异常／边界：混合 str/bytes、空 chunk、非法元素类型、迭代中抛错和编码跨块有明确错误。
- 原生回归：tests/test_xmltodict.py:test_streaming_generator/string_vs_file
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．显式增量 feed 与 close 解析对象（增强提案）

- 来源／场景：[xmltodict.py:parse 的局部 parser 生命周期](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：一次 parse 独占 parser，不可从事件循环多次调用 feed 后 close。
- 交付目标：提供 Parser 对象，feed 接收片段、close 完成输入并返回结果，公开状态与关闭语义。
- 影响模块：xmltodict.py:parse 与新 Parser
- 兼容边界：同步 parse 继续可用并复用同一内核，不隐式产生后台线程或网络读取。
- 正常验收：按字节边界多次 feed、close 后得到与 parse 相同订单对象。
- 异常／边界：close 两次、close 后 feed、解析错误后复用拒绝，截断输入定位正确。
- 原生回归：tests/test_xmltodict.py；新增增量状态回归
- 真实依赖：03

## 05．自然迭代的流式条目接口（增强提案）

- 来源／场景：[xmltodict.py:parse 的 item_depth/item_callback](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：只有同步回调式消费，使用方需自己桥接为迭代器。
- 交付目标：提供 iter_items(source,item_depth)，按需 feed 并 yield 条目，支持 close。
- 影响模块：xmltodict.py:Parser 与 streaming endElement
- 兼容边界：已有 callback 语义保持，迭代时不保留全部条目；不能用无限内存队列冒充惰性。
- 正常验收：只取前两条时只读取有界 chunk；完整迭代内容与 callback 模式一致。
- 异常／边界：提前关闭释放自有输入、调用方流不越权关闭，单条大项受预算限制。
- 原生回归：tests/test_xmltodict.py 的 streaming_memory_usage 与匹配集合
- 真实依赖：02, 04

## 06．按元素路径选择流式条目（增强提案）

- 来源／场景：[xmltodict.py:_DictSAXHandler.endElement](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：item_depth 会接收该深度所有节点，不能原生只选 orders/order。
- 交付目标：增加受限 item_path 选择器，只向消费者发出指定路径匹配项。
- 影响模块：xmltodict.py:路径维护与 streaming 回调
- 兼容边界：不引入完整 XPath 或表达式执行；明确命名空间按 URI 展开名匹配。
- 正常验收：同深度 metadata 和 order 并存，只得到 order，路径可含单段通配。
- 异常／边界：空路径、非法通配、namespace、重复层级、未匹配结果为空而非错误。
- 原生回归：tests/test_xmltodict.py 的 namespaces/streaming
- 真实依赖：05

## 07．早期跳过无需构建的子树（增强提案）

- 来源／场景：[xmltodict.py:_DictSAXHandler.startElement/push_data](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：postprocessor 到节点完成才可丢值，仍会构建大块无关子树。
- 交付目标：增加 element_filter(path,attrs)，起始事件即可跳过子树字典与文本累积。
- 影响模块：xmltodict.py:SAX 起止／字符回调
- 兼容边界：XML仍由Expat完整检查；跳过不允许非法XML或实体，不伪称停止读取源。
- 正常验收：过滤 payload 后订单字段保持，巨大忽略区不会进入结果。
- 异常／边界：嵌套跳过、回调异常、全部过滤、流式选中项内过滤和路径恢复正确。
- 原生回归：tests/test_xmltodict.py 的 postprocessor_skip/streaming
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．可选按顺序保存混合内容（增强提案）

- 来源／场景：[xmltodict.py:_DictSAXHandler.data/children；上游 AGENTS.md caveats](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：默认把字符数据合并为 #text，不能保留文字与子元素交错顺序，项目已明确非目标。
- 交付目标：新增单独 ordered_content 模式，用 #content 节点列表表示文本与子元素顺序并支持反向输出。
- 影响模块：xmltodict.py:handler 与 _emit
- 兼容边界：默认 dict 结构完全保持；本地 opt-in 扩展不声称上游要转成完整 XML DOM。
- 正常验收：p 中“前文+b+后文+i+结尾”往返后独立解析得到相同文字／子节点顺序。
- 异常／边界：相邻文本、空内容、重复子标签、pretty 不插入语义空白，未知节点拒绝。
- 原生回归：tests/test_xmltodict.py 的 semi_structured；tests/test_dicttoxml.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．可选处理指令记录与输出（增强提案）

- 来源／场景：[xmltodict.py:parse 注册的 Expat handlers](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：没有 ProcessingInstructionHandler，XML处理指令不会进入普通结果。
- 交付目标：提供 process_instructions，表示 target/data 并在有序模式原位置输出。
- 影响模块：xmltodict.py:parse handlers；_XMLGenerator
- 兼容边界：默认忽略处理指令保持；不执行指令、不访问其 URL，不允许冒充 XML 声明。
- 正常验收：合成 xml-stylesheet PI 读出并回写 target/data，前后位置保持。
- 异常／边界：非法 target、包含 ?>、多条顶层PI、None数据与编码错误明确。
- 原生回归：tests/test_xmltodict.py；tests/test_dicttoxml.py
- 真实依赖：08

## 10．CDATA 节点的显式表示与写出（增强提案）

- 来源／场景：[xmltodict.py:_should_force_cdata 与 _emit](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：force_cdata 只强制 #text 容器，不保存或生成真正 CDATA 边界。
- 交付目标：提供显式 CDATA 值／process_cdata 选项，在有序模式记录 CDATA 文本并安全输出。
- 影响模块：xmltodict.py:Start/EndCdata handlers；_XMLGenerator
- 兼容边界：原 force_cdata 名称和语义保持；CDATA内容不能被当作原始XML插入。
- 正常验收：含 < 与 & 的 CDATA 文本往返值一致，边界在选定模式保留。
- 异常／边界：文本含 ]]> 安全拆分或明确拒绝；空区段、混合文字和编码回归。
- 原生回归：tests/test_xmltodict.py 的 force_cdata；tests/test_dicttoxml.py
- 真实依赖：08

## 11．注释内容可选按 XML 注释语义保真（增强提案）

- 来源／场景：[xmltodict.py:_XMLGenerator.comment](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：当前 escape 注释里的 &/<，再次parse得到实体字面文本；已观察 A&B 变 A&amp;B，项目只承诺best-effort。
- 交付目标：增加 comment_text=verbatim 模式，保留合法注释文本，仅校验 -- 和末尾 - 等注释约束。
- 影响模块：xmltodict.py:_validate_comment/_XMLGenerator.comment
- 兼容边界：默认现有转义可先保持；不把注释内容当普通元素文本或无校验 rawXML。
- 正常验收：含 A&B <x> 注释按选定模式读写相同，默认模式回归。
- 异常／边界：--、末尾-、非法字符、空注释、bytes编码与comment_key冲突明确。
- 原生回归：tests/test_xmltodict.py:test_comments；tests/test_dicttoxml.py 的 comments
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．遵守 xml:space 的局部空白规则（增强提案）

- 来源／场景：[xmltodict.py:_DictSAXHandler.endElement](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：strip_whitespace 是全局开关，xml:space=preserve 的文本本轮仍被 strip。
- 交付目标：增加 honor_xml_space，继承 preserve/default 并影响当前子树文本处理。
- 影响模块：xmltodict.py:startElement/endElement 的空白状态
- 兼容边界：默认全局策略保持；显式 False 仍可保留全局空白，命名空间模式识别相同 XML 命名空间。
- 正常验收：preserve 节点保留两侧空格，嵌套 default 恢复既定剔除策略。
- 异常／边界：无效 xml:space 值、空文本、注释和流式回调一致，混合内容模式不插额外空白。
- 原生回归：tests/test_xmltodict.py 的 keep_whitespace/skip_whitespace
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．输出时生成必要命名空间声明（增强提案）

- 来源／场景：[xmltodict.py:_process_namespace/_emit](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：namespaces 做名字映射，但调用方仍需安排 @xmlns，缺少统一声明策略。
- 交付目标：新增 namespace_policy，按 URI→prefix 注册表输出 QName 和最小需要的 xmlns。
- 影响模块：xmltodict.py:_process_namespace/_emit
- 兼容边界：默认原字典 @xmlns 保持；不覆盖调用方冲突声明，属性的默认命名空间规则单独处理。
- 正常验收：两个URI元素与属性生成可由Expat命名空间模式读回相同展开名的XML。
- 异常／边界：同前缀映射多URI、保留xml/xmlns、嵌套遮蔽与默认namespace切换明确。
- 原生回归：tests/test_xmltodict.py 的 namespace；tests/test_dicttoxml.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．命名空间压缩后的键碰撞策略（增强提案）

- 来源／场景：[xmltodict.py:_build_name/push_data](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：多个URI映射到同一短名时按普通重复键合并列表，没有区分不同原始展开名的可选诊断。
- 交付目标：增加 namespace_collisions=merge/warn/error，保存必要原始名字用于判别。
- 影响模块：xmltodict.py:handler 名称映射与 push_data
- 兼容边界：默认 merge 保持；同一原始标签合法重复不视作碰撞。
- 正常验收：两个URI映射为同短名在error模式拒绝，merge仍产原结果。
- 异常／边界：属性与子元素碰撞、命名空间关闭、回调重命名、诊断不含节点值。
- 原生回归：tests/test_xmltodict.py 的 namespace_collapse 与 force_list
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．按路径声明标量编解码（增强提案）

- 来源／场景：[xmltodict.py:postprocessor/preprocessor 扩展点](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：可自己写回调，但没有路径绑定的双向 codec 注册，所有文本默认str。
- 交付目标：提供 opt-in codecs，将指定路径的整数、Decimal、布尔等转换及写出按显式策略配对。
- 影响模块：xmltodict.py:handler 与 unparse 值转换
- 兼容边界：不自动猜类型，不宣称XSD验证；原postprocessor顺序明确且保留默认字符串。
- 正常验收：订单qty读为int、金额保留Decimal精度，回写后独立读出同值。
- 异常／边界：非法字面量、None/空串、重复标签、属性路径、超范围值带位置报错。
- 原生回归：tests/test_xmltodict.py 的 postprocessor；tests/test_dicttoxml.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．转换错误附带 XML 源位置（增强提案）

- 来源／场景：[xmltodict.py:parse 的局部 parser；postprocessor](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：Expat语法异常有位置，但用户postprocessor错误缺少统一path/line/column包装。
- 交付目标：增加诊断模式的 ConversionError，保留原异常链并提供路径和Expat当前行列。
- 影响模块：xmltodict.py:parse 与 handler 回调桥接
- 兼容边界：默认原异常传播保持；默认不把原始文本／属性值写入异常。
- 正常验收：某条qty转换失败可定位对应元素路径及行列，文件和chunk输入一致。
- 异常／边界：属性错误、空元素、回调主动ParsingInterrupted、异常链和编码位移说明明确。
- 原生回归：tests/test_xmltodict.py 的 postprocessor/streaming
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．输出前的完整字典预检（增强提案）

- 来源／场景：[xmltodict.py:unparse/_emit](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：写入提供的 output 时，较深处非法键／多根可能在前半段已输出后才抛错。
- 交付目标：新增 validate_document，返回有路径的全部结构问题，可在unparse前显式运行。
- 影响模块：xmltodict.py:_validate_name/_validate_comment/_emit
- 兼容边界：预检本身不写输出；不可重复生成器要明确拒绝或由调用者选择冻结，不承诺任意流原子回滚。
- 正常验收：多处非法键一次得到位置清单，合法字典预检后输出被独立解析器接受。
- 异常／边界：循环对象、多个根、无根、非法控制字符、坏comment、bytes解码错误完整定位。
- 原生回归：tests/test_dicttoxml.py 的 validation/security/roots
- 真实依赖：01

## 18．按需产生 XML 输出片段（增强提案）

- 来源／场景：[xmltodict.py:unparse(output=None) 与 XMLGenerator](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：output 可写流已存在，但不提供自然拉取的字符串／字节迭代器。
- 交付目标：提供 iter_unparse，以有界片段队列拉取序列化结果，适配调用方网络或压缩管道。
- 影响模块：xmltodict.py:_emit/_XMLGenerator 与新输出桥
- 兼容边界：不以整体unparse后切块冒充流式；既有字符串和output API保持。
- 正常验收：只拉取首片段就开始输出，拼接后等同unparse，单次消费大子项生成器。
- 异常／边界：提前关闭释放生成器、编码跨片段、序列化中途错误可观察且不报完整成功。
- 原生回归：tests/test_dicttoxml.py；新增有界输出回归
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．显式 XML 片段解析（增强提案）

- 来源／场景：[xmltodict.py:parse；unparse(full_document=False)](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：unparse 可输出多个根片段，parse 仍要求完整单根 XML，无法对应读回片段集合。
- 交付目标：新增 parse_fragment/iter_fragment，使用受控合成根并返回独立顶层节点序列。
- 影响模块：xmltodict.py:parse 输入适配；handler 根处理
- 兼容边界：默认parse仍严格单根；不允许片段自带DOCTYPE/XML声明混入中间，不执行实体。
- 正常验收：两个同名顶层片段按顺序读为两个节点，与完整文档模式区分。
- 异常／边界：顶层文字、注释、PI、截断片段、命名空间继承和超预算明确。
- 原生回归：tests/test_xmltodict.py；tests/test_dicttoxml.py 的 full_document
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．可重复的属性排序输出策略（增强提案）

- 来源／场景：[xmltodict.py:_emit 中 attrs 字典构建](https://github.com/martinblech/xmltodict/blob/6e29fba282e68631034dd2722a413b4e35276584/xmltodict.py)
- 原版现状：属性序沿输入mapping顺序，缺少显式确定性渲染profile，逻辑等价字典可能产生不同快照。
- 交付目标：增加 sort_attributes 选项，按约定展开名排序属性并稳定xmlns声明。
- 影响模块：xmltodict.py:_emit 的 AttributesImpl 构建
- 兼容边界：默认保留输入顺序；只定义确定性展示，不声称 W3C C14N、数字签名或重排子元素。
- 正常验收：不同插入顺序的同一属性集生成完全相同字节，文本和子元素顺序不变。
- 异常／边界：namespace声明、Unicode名、默认属性、pretty/encoding与自定义prefix组合一致。
- 原生回归：tests/test_dicttoxml.py 的 attribute/namespace/pretty
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
