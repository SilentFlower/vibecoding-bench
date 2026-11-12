# markdown-it-py：二十步真实工程路线

固定 [executablebooks/markdown-it-py@6f586542653a56d2ee8549a0dccfaa6ba5ebe14a](https://github.com/executablebooks/markdown-it-py/tree/6f586542653a56d2ee8549a0dccfaa6ba5ebe14a)。原生基线 1032 通过、0 跳过；范围和限制见 [单仓审查](./markdown-it-py.md)。类型计数：{"修复": 9, "增强": 11}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．图片 alt 保留转义与实体文本（修复）

- 来源／实际场景：[上游 #445](https://github.com/executablebooks/markdown-it-py/issues/445)固定版复现。
- 原版现状：image.children里的text_special未被text_join转成text，alt丢*和&。
- 用户交付：图片替代文字与可读行内文本一致，转义字符和实体语义保留。
- 影响模块：rules_core/text_join.py；renderer.py:image/renderInlineAsText。
- 兼容边界：不把强调标签本身写进alt；HTML属性继续转义。
- 正常验收：星号、&amp;、&lt;及混合强调得到完整alt。
- 边界／错误验收：图片嵌套描述、空alt、代码span及链接对照不重复转义。
- 原生回归：tests/test_cmark_spec/test_spec.py、tests/test_port/test_fixtures.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．插件匹配但不前进时快速失败（修复）

- 来源／实际场景：[上游 #441](https://github.com/executablebooks/markdown-it-py/issues/441)；block/inline各0.5秒超时。
- 原版现状：返回True却不改line/pos时tokenize持续循环。
- 用户交付：检测匹配后位置未严格前进，抛包含规则名/位置的明确错误。
- 影响模块：parser_block.py:tokenize；parser_inline.py:tokenize/skipToken；ruler.py。
- 兼容边界：合法规则和silent验证行为保持；异常不给出貌似成功的部分文档。
- 正常验收：不前进block/inline规则在很小预算内报错，正常插件仍通过。
- 边界／错误验收：后退位置、只推token不移动、silent分支、maxNesting分别受控，不产生增长到OOM。
- 原生回归：tests/test_api/test_plugin_creation.py、tests/test_fuzzer.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．未闭合链接不吞后续代码片段（修复）

- 来源／实际场景：[上游 #438](https://github.com/executablebooks/markdown-it-py/issues/438)三例实际重放。
- 原版现状：[foo `bar` baz`等输出整段字面反引号。
- 用户交付：失败的链接/图片前瞻恢复backtick等扫描状态，后续合法code span可识别。
- 影响模块：helpers/parse_link_label.py；rules_inline/backticks.py；rules_inline/link.py/image.py。
- 兼容边界：无效链接仍字面；正常链接、合法未匹配反引号规则保持。
- 正常验收：三例得到代码节点bar/code/a而前缀括号保留。
- 边界／错误验收：多种反引号长度、嵌套括号、转义、已闭合链接无跨状态污染。
- 原生回归：tests/test_cmark_spec/test_spec.py、tests/test_port/test_fixtures.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．HTML 块匹配遵守 ASCII 与小写声明规则（修复）

- 来源／实际场景：[上游 #437](https://github.com/executablebooks/markdown-it-py/issues/437)，仓内/官方CommonMark0.31.2核对。
- 原版现状：<!doctype html>不打断段落，<ſcript>误作script块。
- 用户交付：声明接受ASCII字母大小写，HTML标签大小写匹配限ASCII。
- 影响模块：rules_block/html_block.py:HTML_SEQUENCES。
- 兼容边界：保留标准SCRIPT混合大小写与html=False模式，不能扩大任意Unicode标签为HTML。
- 正常验收：小写doctype独立HTML块，ſcript按普通文本安全转义。
- 边界／错误验收：İ/ı/K等Unicode casefold边界、完整script/style/pre/textarea开闭保持。
- 原生回归：tests/test_cmark_spec/test_spec.py、tests/test_html_inline.py、tests/test_port/test_whitespace.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．列表结束后的 type-7 HTML 边界（修复）

- 来源／实际场景：[上游 #434](https://github.com/executablebooks/markdown-it-py/issues/434)；## Opts/- a/<br>/## Next。
- 原版现状：br留在li内，Next误成第二标题。
- 用户交付：修正容器退出后的块起始判定，让外层type-7 HTML按规范延续至空行。
- 影响模块：rules_block/list.py、rules_block/html_block.py、parser_block.py。
- 兼容边界：不是让type-7任意打断同一普通段落；保留无HTML模式。
- 正常验收：列表关闭后br与Next同属HTML块，不再产生伪heading token。
- 边界／错误验收：带空行、span/img、嵌套引用/列表和缩进HTML分别符合规范。
- 原生回归：tests/test_cmark_spec/test_spec.py、tests/test_port/test_fixtures.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．消除解析制造的空 text 节点（修复）

- 来源／实际场景：[上游 #374](https://github.com/executablebooks/markdown-it-py/issues/374)，nested emphasis实测。
- 原版现状：_li**ne**_结束后额外空text节点，树消费者需跳过。
- 用户交付：清理解析器生成的无语义空text，并保持真实空插件节点契约。
- 影响模块：rules_inline/fragments_join.py、rules_core/text_join.py；tree.py。
- 兼容边界：不要无条件删除自定义meta承载的插件token；HTML与原始文本语义保持。
- 正常验收：嵌套强调树不再有空text，walk结果简洁且渲染等价。
- 边界／错误验收：仅空输入、空链接文本、代码/图片子token、插件meta不被误删。
- 原生回归：tests/test_tree.py、tests/test_port/test_fixtures.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．reset_rules 异常退出仍恢复（修复）

- 来源／实际场景：main.py:reset_rules实际RuntimeError观察。
- 原版现状：yield后无finally，异常后emphasis仍关闭。
- 用户交付：用可靠退出收口恢复四条规则链的启用集合。
- 影响模块：main.py:MarkdownIt.reset_rules；ruler.py。
- 兼容边界：正常退出行为保持；不承诺撤销规则函数替换等未声明状态。
- 正常验收：异常和正常离开后active规则与进入前完全一致。
- 边界／错误验收：嵌套上下文、原已禁用规则、异常原样传播，不被恢复过程吞没。
- 原生回归：tests/test_api/test_main.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．规则启停支持一次性 Iterable（修复）

- 来源／实际场景：main.enable/disable标注Iterable；迭代器与list实际对照。
- 原版现状：core链先消耗迭代器，block/inline实际未启用table/strikethrough且不报错。
- 用户交付：在多链分发前固定一次名称集合，所有链和missed检测得到同样输入。
- 影响模块：main.py:enable/disable；ruler.py:enable/disable。
- 兼容边界：字符串、list及ignoreInvalid语义保持，不增加虚假规则。
- 正常验收：list/tuple/generator启用和禁用得到相同active集与HTML。
- 边界／错误验收：未知名称、重复名称、空iterable和中途迭代异常不留下意外半状态。
- 原生回归：tests/test_api/test_main.py、tests/test_api/test_plugin_creation.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．未注册引用的解析回调（增强）

- 来源／实际场景：[上游 #385](https://github.com/executablebooks/markdown-it-py/issues/385)；动态文档索引。
- 原版现状：没有references或查不到key时直接返回False，需复制link规则。
- 用户交付：提供可选broken_reference_resolver，返回目标/title或放弃，支持链接和图片。
- 影响模块：rules_inline/link.py/image.py；main.py配置与utils.py类型。
- 兼容边界：默认字面保持；解析结果仍normalizeLink/validateLink，不访问网络。
- 正常验收：动态名字映射到本地文档路径，显式定义优先。
- 边界／错误验收：回调异常/非法scheme/空返回、shortcut/collapsed/full引用与silent模式明确，不重复调用副作用。
- 原生回归：tests/test_port/test_references.py、tests/test_api/test_main.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．高亮器显式声明完整代码块（增强）

- 来源／实际场景：[上游 #256](https://github.com/executablebooks/markdown-it-py/issues/256)及div/pre回调重放。
- 原版现状：仅startswith(<pre)免包裹，div高亮块被再次包进pre/code。
- 用户交付：允许高亮回调返回带block/inline标记的结果或明确配置，避免脆弱字符串猜测。
- 影响模块：renderer.py:RendererHTML.fence；utils.py高亮类型。
- 兼容边界：旧str回调与<pre启发式保持；回调本来就是可信生成HTML，不伪称清洗。
- 正常验收：完整div高亮结果仅一层代码容器，inline高亮仍按语言class包裹。
- 边界／错误验收：空结果fallback、异常、非str错误、首空白与换行处理明确定义。
- 原生回归：tests/test_api/test_main.py、tests/test_port/test_fixtures.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．行内 token 精确源位置（增强）

- 来源／实际场景：[上游 #219](https://github.com/executablebooks/markdown-it-py/issues/219)；编辑器定位链接。
- 原版现状：块map是行范围，行内link/text的map均None。
- 用户交付：opt-in记录行内源span和行列，嵌套/规范化保留原始坐标映射。
- 影响模块：rules_inline/state_inline.py、rules_core/inline.py、token.py、tree.py。
- 兼容边界：原map两行范围不改类型；新增字段走meta或明确新类型，默认token快照兼容。
- 正常验收：链接/代码span可精确高亮原源文本。
- 边界／错误验收：CRLF、制表符、Unicode码点、实体与转义映回原始输入，不按渲染文本猜列。
- 原生回归：tests/test_api/test_token.py、tests/test_tree.py、tests/test_port/test_whitespace.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．原生纯文本 renderer（增强）

- 来源／实际场景：[上游 #103](https://github.com/executablebooks/markdown-it-py/issues/103)；Markdown语料NLP。
- 原版现状：仅内置HTML renderer；已有RendererProtocol可扩展。
- 用户交付：提供PlainText renderer，段落/列表/代码/链接/图片alt具有可读分隔。
- 影响模块：renderer.py或独立renderer模块；CLI格式入口。
- 兼容边界：默认HTML不变；原始HTML可选择剥离或保留文本，不自称安全HTML过滤。
- 正常验收：文档导出保留阅读顺序、代码与alt，去掉Markdown标记。
- 边界／错误验收：空文档、软硬换行、raw HTML、未知插件token有显式fallback。
- 原生回归：tests/test_api/test_main.py、tests/test_tree.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 13．Markdown 重排 renderer（增强）

- 来源／实际场景：[上游 #10](https://github.com/executablebooks/markdown-it-py/issues/10)；文档格式化。
- 原版现状：token可转dict但没有原生Markdown renderer。
- 用户交付：从token生成可重解析Markdown，首版支持核心CommonMark及显式列表/围栏策略。
- 影响模块：新增Markdown renderer；token.py；renderer接口。
- 兼容边界：目标是语义往返，非字节还原；未知插件必须报不支持或注册规则。
- 正常验收：标题、列表、链接、围栏重排后parse结构语义等价。
- 边界／错误验收：反引号长度、标题尾#、引用空行、转义实体和代码含围栏不误闭合。
- 原生回归：tests/test_cmark_spec/test_spec.py、tests/test_port/test_fixtures.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 14．CLI 不静默丢弃坏 UTF-8（修复）

- 来源／实际场景：cli.parse.convert_file使用errors=ignore，实际含0xff文件。
- 原版现状：退出0输出beforeafter，坏字节被吞且无诊断。
- 用户交付：默认严格解码并显示文件/位置；可选显式replace或ignore供旧数据处理。
- 影响模块：cli/parse.py:convert_file/parse_args。
- 兼容边界：有效UTF-8输出保持；显式兼容开关才能继续丢字节。
- 正常验收：合法中文文件成功，非法字节非0且说明编码错误。
- 边界／错误验收：首中尾坏字节、BOM、多个文件部分失败及stdin策略一致，不打印原始敏感全文。
- 原生回归：tests/test_cli.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．CLI 导出 token JSON（增强）

- 来源／实际场景：原生Token.as_dict已存在但CLI只HTML；编辑器/流水线需要序列化。
- 原版现状：help无tokens或format开关。
- 用户交付：CLI提供--format tokens，按每文档结构输出合法JSON并标明输入来源。
- 影响模块：cli/parse.py；token.py:as_dict。
- 兼容边界：默认HTML与已有多文件顺序保持；明确多文档JSON数组或NDJSON，不拼成无效JSON。
- 正常验收：输出经json读取后Token.from_dict往返核心字段。
- 边界／错误验收：中文/空文档/多文件、不可序列化meta明确处理，诊断走stderr。
- 原生回归：tests/test_cli.py、tests/test_api/test_token.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．CLI 输出路径与多文件产物（增强）

- 来源／实际场景：现有多文件只拼stdout；希望独立落盘而非shell重定向。
- 原版现状：无--output/output-dir，不提供产物冲突处理。
- 用户交付：增加单文件-o与多文件output-dir，保持每文件独立env和相对名。
- 影响模块：cli/parse.py:convert/convert_file。
- 兼容边界：stdout仍默认；不自动递归扫描、不覆盖未选择目录。
- 正常验收：两个带独立reference文件分别生成正确HTML。
- 边界／错误验收：输入输出同路径、同名冲突、目录/权限失败、已存在文件覆盖政策明确且不中途伪成功。
- 原生回归：tests/test_cli.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．CLI 暴露预设与声明式解析配置（增强）

- 来源／实际场景：main.py已有commonmark/zero/gfm-like等与options；CLI仅tables开关。
- 原版现状：无法在CLI选择preset、html开关、linkify或typographer。
- 用户交付：提供--preset及有限声明式options入口，校验类型/未知键并显示生效配置。
- 影响模块：cli/parse.py:parse_args/main；presets与utils.py。
- 兼容边界：默认commonmark保持；不从配置自动导入任意Python回调；可选依赖缺失清楚提示。
- 正常验收：CLI选择zero/commonmark/可用GFM得到与API相同结果。
- 边界／错误验收：冲突参数、未知preset、错误bool、缺linkify依赖与不可信HTML开关边界明确。
- 原生回归：tests/test_cli.py、tests/test_api/test_main.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．可选深度复制 token（增强）

- 来源／实际场景：Token.copy明确浅拷贝，renderer源码也提及deepClone；并行文档变换场景。
- 原版现状：修改copy.children/meta会改原token，as_dict/from_dict也不保证任意meta独立。
- 用户交付：提供deep_copy或copy(deep=True)，递归复制children/attrs/map和可支持meta。
- 影响模块：token.py:Token.copy/from_dict。
- 兼容边界：旧copy浅语义保持；自定义不可复制meta采用显式策略而非默默共享。
- 正常验收：修改副本子token/attrs/map/meta列表不影响原始缓存。
- 边界／错误验收：循环meta、不可复制对象、深层children与自定义meta copier明确失败/处理。
- 原生回归：tests/test_api/test_token.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．语法树受控移动与删除（增强）

- 来源／实际场景：SyntaxTreeNode.children暴露list，手动append会出现旧parent/双重归属。
- 原版现状：无append/replace/remove工具；把child放另一tree仍指向旧parent。
- 用户交付：提供显式树编辑方法同步parent/siblings，拒绝循环/非法root移动，to_tokens反映修改。
- 影响模块：tree.py:SyntaxTreeNode.children/parent/to_tokens。
- 兼容边界：现有只读walk/索引保持；不假称直接改公开list自动获得同样保证。
- 正常验收：移动段落、删除列表项和替换子树后父链与tokens一致。
- 边界／错误验收：自插入、祖先插入、重复子节点和不同token引用共享策略明确。
- 原生回归：tests/test_tree.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 20．显式获取必需源行范围（增强）

- 来源／实际场景：[上游 #430](https://github.com/executablebooks/markdown-it-py/issues/430)；fence消费者类型收窄。
- 原版现状：map类型Optional，需要每个调用者重复断言且无清楚错误。
- 用户交付：Token和SyntaxTreeNode提供require_map，返回验证过的范围或带token类型的异常。
- 影响模块：token.py、tree.py:map。
- 兼容边界：保留可选map原属性；不伪造缺失行号，不依赖11的精确行内span。
- 正常验收：fence/html_block返回真实半开行范围，返回值不会意外改原map。
- 边界／错误验收：无map/root、畸形长度、逆序/负值有清晰错误，原始合法[0,0]空范围明确。
- 原生回归：tests/test_api/test_token.py、tests/test_tree.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

现有line map、Token.as_dict/from_dict、浅copy、SyntaxTreeNode.walk/to_tokens、RendererProtocol、env上下文、规则启停、linkify和preset均保留。line map已存在，新增仅针对缺失的行内精确位置或显式require_map；不把#354旧抽象接口诉求当作仍缺RendererProtocol。当前任务列表/alerts等内置能力不作为新项目特性凑数。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
