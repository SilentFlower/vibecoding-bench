# html5lib：二十步真实工程迭代路线

固定 [html5lib/html5lib-python@fd4f032bc090d44fb11a84b352dad7cbee0a4745](https://github.com/html5lib/html5lib-python/tree/fd4f032bc090d44fb11a84b352dad7cbee0a4745)，原生证据见 [单仓审查](./html5lib.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．DOCTYPE令牌字段类型校验

- **来源／场景**：自定义treewalker把文档声明送入原生lint；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/filters/lint.py)。
- **原版缺口**：Doctype分支对publicId/systemId错误重复检查name；实测42和空list仍被接受
- **交付及模块**：分别校验两个标识字段自身的None/字符串合同，给出对应字段错误；`html5lib/filters/lint.py:Filter`。
- **兼容与实际依赖**：不改变合法DOCTYPE和None标识；仅修复原有类型断言漏检；步骤依赖：无。
- **正常验收**：html名称及字符串public/system标识通过，数值/容器类型被明确拒绝
- **异常／边界验收**：name为None与标识为字符串仍合法；两个字段分别错误及空串都有确定结果
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 02．令牌流结束时检查未闭合元素

- **来源／场景**：转换器想确认自定义walker产生配对标签；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/filters/lint.py)。
- **原版缺口**：require_matching_tags=True只在EndTag时pop，结束时不检查栈；仅section StartTag实测通过
- **交付及模块**：在完整迭代结束校验剩余open_elements，报告未闭合元素；`html5lib/filters/lint.py:Filter`。
- **兼容与实际依赖**：require_matching_tags=False继续允许片段流；void元素不要求关闭；消费者提前停止不误称已校验完整流；步骤依赖：无。
- **正常验收**：section正常开闭通过，缺EndTag的完整流拒绝
- **异常／边界验收**：空流、嵌套、错序关闭、孤立EndTag及void元素均有稳定诊断
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 03．现代template内容片段语义

- **来源／场景**：归档文档包含可复用的HTML模板；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/html5parser.py)。
- **原版缺口**：原版phase表无template插入模式，实跑只得到普通元素子树，无独立模板内容片段
- **交付及模块**：补齐显式版本配置的template构树与内容片段，并联动walker/serializer；`html5lib/html5parser.py`, `html5lib/treebuilders/base.py`, `html5lib/serializer.py`。
- **兼容与实际依赖**：作为现代HTML兼容增强明确选择版本；旧构树模式可保持，不冒称固定历史规范中的新发现缺陷；步骤依赖：无。
- **正常验收**：template中表格及嵌套template按选择的规范形成内容片段并可序列化
- **异常／边界验收**：template结束错配、table上下文、EOF和不同树后端能力不足均明确处理
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 04．带命名空间的片段上下文

- **来源／场景**：编辑器要解析SVG或MathML元素内部片段；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/html5parser.py)。
- **原版缺口**：parseFragment仅container字符串，svg字符串仍生成HTML命名空间circle；没有上下文元素命名空间/属性合同
- **交付及模块**：新增FragmentContext，包含namespace/localname及影响集成点的属性；`html5lib/html5parser.py:parseFragment`, `html5lib/treebuilders/base.py`。
- **兼容与实际依赖**：原container字符串保持HTML语义；新上下文显式使用，不依靠名称猜测SVG；步骤依赖：无。
- **正常验收**：SVG circle及MathML片段形成正确命名空间，HTML div结果与原版相同
- **异常／边界验收**：foreignObject和annotation-xml集成点、未知namespace及非字符串属性按清楚规则处理
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 05．稳定的公开词法令牌迭代器

- **来源／场景**：文档工具只需观察实体和标签词法，不需要完整树；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/_tokenizer.py)。
- **原版缺口**：实际HTMLTokenizer位于私有_tokenizer且数字type合同与walker文本type不同，顶层没有公开tokenize
- **交付及模块**：新增稳定Token类型及tokenize迭代器，明确词法事件与修复后树事件差异；`html5lib/_tokenizer.py`, `html5lib/__init__.py`, `html5lib/constants.py`。
- **兼容与实际依赖**：保留私有tokenizer给parser使用；不把词法令牌承诺为平衡树，不误称原版没有流式内部迭代；步骤依赖：无。
- **正常验收**：普通Unicode/bytes文档按顺序产生标签、文字和错误事件
- **异常／边界验收**：重复属性、实体、注释、原始文本及解码错误有确定事件，提前关闭释放自有输入
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 06．可选择的解析诊断策略

- **来源／场景**：导入工具允许缺省DOCTYPE，但对特定格式错误要求停止；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/html5parser.py)。
- **原版缺口**：errors已有行列/code/datavars；strict只能首错抛出，缺按code选择与结构化严重级别
- **交付及模块**：新增DiagnosticPolicy与结构化诊断返回/回调，按代码决定记录、忽略或停止；`html5lib/html5parser.py:parseError`, `html5lib/constants.py:E`。
- **兼容与实际依赖**：默认errors列表与strict行为保持；不把默认恢复改为严格解析；步骤依赖：无。
- **正常验收**：缺DOCTYPE可忽略，指定错配代码可停止，全部错误包含已格式化消息与原代码
- **异常／边界验收**：未知代码、消息参数不齐、回调异常和重新解码后的重复事件有明确合同
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 07．树节点到原文位置映射

- **来源／场景**：编辑器要把树中的内容定位到原HTML；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/_inputstream.py)。
- **原版缺口**：输入流只有当前行列，构树节点不保存来源；实体/隐含节点/重排后不能可靠反查
- **交付及模块**：增加opt-in SourceMap，保留字符/字节跨度及合成、合并、重排来源；`html5lib/_inputstream.py`, `html5lib/_tokenizer.py`, `html5lib/treebuilders/base.py`。
- **兼容与实际依赖**：默认节点形状与成本不变；合成tbody不假造源范围；字节偏移仅bytes入口提供；步骤依赖：无。
- **正常验收**：文本与属性能追溯源码，实体多字节和表格修复的来源关系可核对
- **异常／边界验收**：CRLF、重新解码、重复属性、组合字符及跨块令牌映射不越界
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 08．构树修复事件审计

- **来源／场景**：资料维护者要解释为何插入tbody或移动表格前文字；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/html5parser.py)。
- **原版缺口**：debug日志已有tokenizer/phase/process方法/令牌，但没有稳定修复事件及因果节点
- **交付及模块**：新增可选RepairTrace，记录隐含节点、foster parenting与格式重建的有序事件；`html5lib/html5parser.py:mainLoop`, `html5lib/treebuilders/base.py`。
- **兼容与实际依赖**：沿用已有debug能力，不声称缺日志；默认不开启，摘要模式不复制整文档；步骤依赖：无。
- **正常验收**：隐含tbody、自动闭合p及表格重排各能指出修复类型和相关节点
- **异常／边界验收**：相同节点多次移动、EOF隐含结束、重解析和追踪消费者异常保持解析合同
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 09．分块推送式解析会话

- **来源／场景**：应用逐块接收本地文件或编辑器缓冲区；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/_inputstream.py)。
- **原版缺口**：原版可从file-like读取，但只有一次性parse，EOF不能表达暂时缺数据；无feed/finish
- **交付及模块**：新增增量会话，区分need_more与EOF，并延续词法、编码和构树状态；`html5lib/_inputstream.py`, `html5lib/_tokenizer.py`, `html5lib/html5parser.py`。
- **兼容与实际依赖**：保留已有拉取式流读取；不将普通read分块支持说成完全没有流式能力；步骤依赖：无。
- **正常验收**：任意切块与一次性parse的树/错误一致，finish只结算一次
- **异常／边界验收**：实体/UTF8/CRLF跨块、meta重解码、空feed和finish后feed均有明确结果
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 10．树后端能力与数据损失查询

- **来源／场景**：调用方在DOM、etree、lxml之间选择归档后端；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treebuilders/__init__.py)。
- **原版缺口**：getTreeBuilder/getTreeWalker提供工厂，后端限制通过DataLossWarning或异常出现，无统一能力清单
- **交付及模块**：新增后端能力描述及输入特性预检，解释DOCTYPE、注释、非法XML名称等可表达性；`html5lib/treebuilders/__init__.py`, `html5lib/treewalkers/__init__.py`, `html5lib/constants.py`。
- **兼容与实际依赖**：不声称任意后端无损等价，不隐藏既有警告；未安装可选依赖独立标明；步骤依赖：无。
- **正常验收**：查询已安装后端可知full-document/fragment和节点能力，已知损失提前可见
- **异常／边界验收**：缺lxml、自定义后端未知能力、属性namespace和注释限制均不被错误标成功
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 11．后端之间的显式树转换

- **来源／场景**：同一归档流程需把DOM结果交给ElementTree业务；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treeadapters/__init__.py)。
- **原版缺口**：已有walker和Genshi单向adapter，但无通用受支持的convert_tree合同
- **交付及模块**：新增基于walker事件的后端转换，保留可表达节点并返回损失明细；`html5lib/treeadapters/__init__.py`, `html5lib/treebuilders/base.py`, `html5lib/treewalkers/__init__.py`。
- **兼容与实际依赖**：优先复用现有adapter；转换不是重新按HTML修复，不改原树，不保证所有后端无损；步骤依赖：无。
- **正常验收**：DOM到etree及反向转换保留元素、namespace、属性、text/tail顺序
- **异常／边界验收**：DOCTYPE、顶层注释、自定义namespace与目标不能表达的节点明确拒绝或报告
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 12．带编码与兼容模式的解析结果

- **来源／场景**：归档应用需要树与编码决策一起存入元数据；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/html5parser.py)。
- **原版缺口**：documentEncoding已有公开属性，compatMode/errors分散在可复用parser上；顶层parse只返树，编码候选来源未公开
- **交付及模块**：新增parse_document结果对象，包含树、编码名称/确定性/来源、兼容模式及诊断快照；`html5lib/html5parser.py`, `html5lib/_inputstream.py:determineEncoding`, `html5lib/__init__.py`。
- **兼容与实际依赖**：原parse继续返回树；明确BOM、override、transport、meta既有优先级不变；不以猜测概率冒充确定性；步骤依赖：无。
- **正常验收**：UTF8 BOM与meta、显式编码和无DOCTYPE文档返回可核对决策
- **异常／边界验收**：Unicode入口不伪造字节编码证据；meta触发重解析、未知编码和parser复用不污染快照
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 13．确定性的语义归档配置

- **来源／场景**：同一文档经不同属性顺序进入归档，需要稳定比较；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/serializer.py)。
- **原版缺口**：serializer已有属性排序、引号、可选标签等选项；没有命名的规范化配置及版本说明
- **交付及模块**：提供versioned canonical profile及摘要入口，组合现有选项并明确语义等价范围；`html5lib/serializer.py:HTMLSerializer`, `html5lib/filters/alphabeticalattributes.py`。
- **兼容与实际依赖**：不把已存在属性排序重计功能；规范化不是原字节无损还原，默认serialize不变；步骤依赖：无。
- **正常验收**：属性重排但语义相同的树产生一致规范串和摘要
- **异常／边界验收**：pre/script空白、namespace前缀、注释及DOCTYPE是否参与比较都显式可选并固定版本
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 14．序列化的损失与替换报告

- **来源／场景**：输出旧编码时维护者要知道哪些字符变成实体；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/serializer.py)。
- **原版缺口**：serializer已有errors与实体替代，但顶层serialize只返字符串，替换范围/类型不汇总
- **交付及模块**：新增serialize_with_report，记录编码替换、无法表达节点和原有serializer错误；`html5lib/serializer.py:HTMLSerializer`, `html5lib/treewalkers/base.py`。
- **兼容与实际依赖**：现有宽容输出和strict选项保持；报告不把正常实体转义自动判为数据丢失；步骤依赖：无。
- **正常验收**：中文输出ASCII时实体替代有计数/位置，UTF8输出无不必要替换
- **异常／边界验收**：代理码点、未知实体、serializer复用及生成器只消费一半的完成状态明确
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 15．保留结构的纯文本导出

- **来源／场景**：归档清单需要可读的正文摘要；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treewalkers/__init__.py)。
- **原版缺口**：walker可取得Characters，但无区分段落、列表、br、pre的文本抽取合同
- **交付及模块**：增加extract_text及块级/空白策略，显式选择标题、列表标记和非正文内容；`html5lib/treewalkers/__init__.py`, `html5lib/filters/whitespace.py`。
- **兼容与实际依赖**：不修改DOM或serializer，不声称简单拼接无法自行实现；新合同集中处理结构语义；步骤依赖：无。
- **正常验收**：段落、br和列表输出自然换行，中文实体正确解码，pre保留所选空白
- **异常／边界验收**：嵌套表格、空块、script/style、hidden及连续空白处理可配置且不遗漏普通tail
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 16．文档链接清单与基准解析

- **来源／场景**：离线资料需要列出引用图片、样式和页面并归档；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treewalkers/__init__.py)。
- **原版缺口**：parser只构树，现有过滤器没有base-aware链接清单及来源位置
- **交付及模块**：新增collect_links，提供元素/属性/原始URI/按base解析URI及去重组；`html5lib/treewalkers/__init__.py`, `html5lib/constants.py`。
- **兼容与实际依赖**：只解析引用不发网络请求；保留原始URI，不把任意URI规范化为文件路径；步骤依赖：无。
- **正常验收**：base href与调用方文档URL按明确优先级解析a/img/link引用
- **异常／边界验收**：片内锚点、空URL、srcset多候选、未知scheme及多个base有稳定记录
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 17．表格逻辑网格导出

- **来源／场景**：资料表格带rowspan/colspan，需要导入业务表格；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treewalkers/__init__.py)。
- **原版缺口**：构树修复表格结构，但没有计算跨行列覆盖关系的业务API
- **交付及模块**：新增extract_table_grid，返回单元格主格、覆盖范围、标题关联及原节点；`html5lib/treewalkers/__init__.py`, `html5lib/treebuilders/base.py`。
- **兼容与实际依赖**：与parse修复算法分离；保留原文和树，不把合并格重复误计为多格；步骤依赖：无。
- **正常验收**：rowspan/colspan混合表格得到正确网格，caption及thead信息保留
- **异常／边界验收**：跨分组跨度、零/非法跨度、重叠布局、嵌套表格及空行有明确诊断
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 18．后端无关的树数据交换

- **来源／场景**：工具之间希望通过JSON交换已解析HTML结构；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treewalkers/__init__.py)。
- **原版缺口**：测试pprint是调试文本，walker是生成器；没有版本化JSON树导入导出合同
- **交付及模块**：新增命名空间感知的tree interchange schema及验证/往返适配；`html5lib/treewalkers/__init__.py:pprint`, `html5lib/treebuilders/base.py`。
- **兼容与实际依赖**：不是jQuery/浏览器DOM替代；注释、DOCTYPE、文本/tail顺序显式表达，不直接序列化后端内部对象；步骤依赖：无。
- **正常验收**：含HTML/SVG/注释的树导出JSON再导入保持约定的语义序列
- **异常／边界验收**：未知schema版本、重复属性、混合内容、深层树及不可表达后端特性明确失败或报告
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 19．结构化HTML树差异

- **来源／场景**：两版归档页面需要知道文字或节点结构改动；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/html5lib/treewalkers/__init__.py)。
- **原版缺口**：只有pprint和序列化，调用方能做文字diff但无节点级增删改与匹配合同
- **交付及模块**：新增diff_trees，按结构和可选稳定id匹配，返回可解释节点/属性/文本变化；`html5lib/treewalkers/__init__.py`, `html5lib/treebuilders/base.py`。
- **兼容与实际依赖**：不默认应用编辑补丁；重复id不强行唯一匹配；属性顺序变化可忽略；步骤依赖：无。
- **正常验收**：插入段落、修改标题和链接属性分别报告，不把纯属性重排当修改
- **异常／边界验收**：重复同形节点、移动子树、namespace改变、注释策略和空树有确定结果
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。

## 20．面向本地批量归档的命令入口

- **来源／场景**：资料管理员一次规范化目录中的多个HTML文件；[固定源码](https://github.com/html5lib/html5lib-python/blob/fd4f032bc090d44fb11a84b352dad7cbee0a4745/parse.py)。
- **原版缺口**：已有根目录parse.py支持单文件/树/HTML输出与profile；未提供可安装的批量清单和机器结果
- **交付及模块**：新增正式console入口及本地清单处理，输出独立结果、诊断JSON和文件映射；`parse.py`, `setup.py`, `html5lib/serializer.py`。
- **兼容与实际依赖**：复用既有单文件选项语义；不把原CLI说成没有；默认不覆盖原文件，显式输出目录；步骤依赖：无。
- **正常验收**：多份UTF8/旧编码HTML得到对应归档结果与逐文件状态
- **异常／边界验收**：路径重名、坏编码、空文件、单项失败继续策略及写出中断有准确退出码和清理
- **原生回归**：`html5lib/tests/test_parser2.py`, `html5lib/tests/test_tokenizer2.py`, `html5lib/tests/test_serializer.py`, `html5lib/tests/test_treewalkers.py`, `html5lib/tests/test_stream.py`, `html5lib/tests/test_encoding.py`, `html5lib/tests/tree_construction.py`。
