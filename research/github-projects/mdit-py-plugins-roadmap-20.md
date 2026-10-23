# mdit-py-plugins：二十步真实工程路线

固定 [executablebooks/mdit-py-plugins@519953da0a394a92534bc27580f4e7415462df44](https://github.com/executablebooks/mdit-py-plugins/tree/519953da0a394a92534bc27580f4e7415462df44)。原生基线 511 通过、0 跳过；范围和限制见 [单仓审查](./mdit-py-plugins.md)。类型计数：{"修复": 12, "增强": 8}。全部尚未实施。

## 二十项独立交付

每项的接口名称属于研究方案；每步包含实现、冻结独立验收、原生累计回归和文档。增强只核对原版能力缺口，不声称原版违反其既有承诺。编号表示累计工程顺序，只有列出的依赖属于真实功能依赖。

### 01．链接正文的www不阻塞行内解析（修复）

- 来源／实际场景：[上游#160](https://github.com/executablebooks/mdit-py-plugins/issues/160)；带see前缀链接真实1秒超时，正常裸www对照完成。
- 原版现状：新增w终止字符与链接嵌套拒绝路径组合时不前进，解析无法结束。
- 用户交付：在链接正文/嵌套排除路径保证回退文本能推进，保留合法自动链接及原链接语义。
- 影响模块：gfm_autolink/index.py:_www_inline_rule；注册终止字符与核心行内接口。
- 兼容边界：不绕过linkLevel产生嵌套a；不依靠修改外部核心来掩盖本插件问题。
- 正常验收：see [www.example.com](https://example.com)有界完成且只含外层链接。
- 边界／错误验收：强调内www、链接开头/中部、不同前缀、普通w密集文本和自动链接规则开关均推进。
- 原生回归：tests/test_gfm_autolink.py；tests/test_gfm.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 02．TeX数学块不越过父块边界（修复）

- 来源／实际场景：[上游#156](https://github.com/executablebooks/mdit-py-plugins/issues/156)；引用内打开、外部闭合真实超时。
- 原版现状：regex匹配全文尾部，endLine内找不到闭合行却仍返回True且state.line不变。
- 用户交付：匹配必须落在当前父块范围，越界先返回False且不push部分Token。
- 影响模块：texmath/index.py:make_block_func/applyRule。
- 兼容边界：保留普通数学和各delimiter语法；五种delimiter只作一项回归矩阵。
- 正常验收：引用内完整数学正常，跨父块例有界回退且后续正文保留。
- 边界／错误验收：嵌套引用/列表/容器、EOF无闭合、silent探测与合法多行不可残留Token/旧state。
- 原生回归：tests/test_texmath.py；tests/test_texmath fixtures。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 03．美元数学内容剥离外层引用缩进（修复）

- 来源／实际场景：[上游#125](https://github.com/executablebooks/mdit-py-plugins/issues/125)；Token.content含换行> x。
- 原版现状：math_block_dollar直接切state.src，保留Markdown引用标记。
- 用户交付：按StateBlock行视图提取内容，去除仅由外层容器引入的标记/缩进，保留实际数学字符。
- 影响模块：dollarmath/index.py:math_block_dollar。
- 兼容边界：顶层公式空白兼容；数学内部真正的>和有意义缩进不可误删。
- 正常验收：引用中多行公式content与去掉外层引用后的数学相同。
- 边界／错误验收：多层引用、列表内公式、空行、首/尾同行内容与source map仍指原始行范围。
- 原生回归：tests/test_dollarmath.py；tests/test_dollarmath/test_plugin_parse.yml。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 04．同行数学闭合后不吞后续列表（修复）

- 来源／实际场景：[上游#147](https://github.com/executablebooks/mdit-py-plugins/issues/147)；b$$ trailing吞下3) $$c。
- 原版现状：同行$$非末尾且非label时继续多行搜索，把其他列表项吸进math_block。
- 用户交付：确定同行闭合/尾部文字策略；不符合块语法则回退行内/正文，不继续吞其他块。
- 影响模块：dollarmath/index.py:math_block_dollar关闭识别。
- 兼容边界：保留已支持的$$x$$与$$x$$ (label)；不把任意后缀当label。
- 正常验收：两列表项及嵌套3)项保持，trailing文字仍可见。
- 边界／错误验收：尾部转义美元、空白/标签、嵌套缩进、无闭合及double_inline组合不跨父块。
- 原生回归：tests/test_dollarmath.py；tests/test_dollarmath fixtures。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 05．span属性同样执行allowed白名单（修复）

- 来源／实际场景：attrs/index.py:_span_rule；allowed=[class]仍输出onclick。
- 原版现状：spans=True分支直接token.attrs=attrs，不调用过滤和insecure_attrs记录。
- 用户交付：统一走属性策略，允许项上Token，拒绝项按约定存meta。
- 影响模块：attrs/index.py:attrs_plugin/_span_rule/_add_attrs。
- 兼容边界：allowed=None仍保留原行为；链接/图片/code已有过滤保持，不悄悄禁用所有span属性。
- 正常验收：[word]{onclick=synthetic .ok}仅class进入HTML，onclick进入insecure_attrs。
- 边界／错误验收：空白名单、id/class重复、嵌套span、单引号/双引号值和错误语法均不旁路。
- 原生回归：tests/test_attrs.py；tests/test_attrs/test_attrs_allowed.yml。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 06．闭合元素连续属性块合并class（修复）

- 来源／实际场景：attrs/index.py:_attr_inline_rule；link连续.first/.second只剩second，code对照正常。
- 原版现状：合并检查的是closing token.attrs，实际属性在opening Token。
- 用户交付：定位opening后从实际目标合并class，保持其他属性覆盖规则。
- 影响模块：attrs/index.py:_find_opening/_attr_inline_rule。
- 兼容边界：后写id/key覆盖仍保持；多个class只按声明拼接，不强行去重改变输出。
- 正常验收：link得到class="first second"，code/image/span同样一致。
- 边界／错误验收：嵌套链接边界、allowed过滤、已有class、空类与找不到opening时不误改邻居。
- 原生回归：tests/test_attrs.py；tests/fixtures/attrs.md。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 07．任务列表后置label保留已解析内容（修复）

- 来源／实际场景：tasklists/__init__.py:todoify/after_label；html=False时粗体和b原文实际重复。
- 原版现状：pop最后child再把原Markdown作为HTML label内容，重复文本并绕过原转义。
- 用户交付：只把真实已解析内容放进label，保持嵌套配对与HTML禁用语义，不重复原文。
- 影响模块：tasklists/__init__.py:todoify/after_label。
- 兼容边界：label=False及包裹label模式保持；随机id用于for配对不作为此次新增能力。
- 正常验收：粗体/链接/转义文本在一个label中正确呈现，原文不重复。
- 边界／错误验收：多行、最后节点是emphasis_close/image/text、html=False、空任务与嵌套列表不丢闭合。
- 原生回归：tests/test_tasklists.py；tests/fixtures/tasklists.md。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 08．任务标记空白判定与checkbox一致（修复）

- 来源／实际场景：tasklists起始regex接受GFM空白而make_checkbox只接受普通空格；tab例无input。
- 原版现状：- [ ]制表符done被标task-list-item但没有复选框。
- 用户交付：解析一次标记状态/尾随空白，把结果用于checkbox与文本移除，覆盖已承诺GFM空白。
- 影响模块：tasklists/__init__.py:starts_with_todo_markdown/todoify/make_checkbox。
- 兼容边界：普通空格/x/X/disabled及enabled配置不变；不扩大成无分隔[x]text。
- 正常验收：tab分隔得到与空格相同checkbox且正文正确。
- 边界／错误验收：CR/LF/多空格、缩进转换、空正文、非GFM空白和label模式同一识别结果。
- 原生回归：tests/test_tasklists.py；tests/fixtures/tasklists.md。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 09．自动链接被拒绝后保留原文字（修复）

- 来源／实际场景：gfm_autolink:_create_autolink先trim pending；自定义validateLink=False实测。
- 原版现状：http://example.com退成://example.com，email退成@example.com。
- 用户交付：先验证规范化链接，再提交pending/token/位置变更；拒绝无副作用回退原文。
- 影响模块：gfm_autolink/index.py:_create_autolink/_protocol_rule/_email_rule。
- 兼容边界：尊重核心自定义normalizeLink/validateLink；合法链接保持，不把拒绝当异常吞文本。
- 正常验收：禁用目标协议/域名后输出完整原字符串且无a标签。
- 边界／错误验收：normalize/validate抛错策略、mailto/xmpp、相邻标点、部分pending和silent探测均一致。
- 原生回归：tests/test_gfm_autolink.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 10．脚注文档前缀安全写入HTML属性（修复）

- 来源／实际场景：footnote render_footnote_anchor_name/ref/open/anchor；合成带引号docId破坏id/href。
- 原版现状：同一docId直接拼进多处属性，产生额外data-probe属性和截断ID。
- 用户交付：明确区分逻辑标识与HTML属性/片段编码，所有引用与回链使用同一规范化结果。
- 影响模块：footnote/index.py:render_footnote_*。
- 兼容边界：简单字符串docId输出保持；自定义anchor_name renderer仍有明确转义契约，不默认更改脚注编号。
- 正常验收：合成引号/空格prefix不破坏DOM属性，ref/定义/backref可对应。
- 边界／错误验收：&/< >、Unicode、重复引用subId、空prefix与多个文档合并无意外重复id。
- 原生回归：tests/test_footnote.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 11．TeX公式编号使用对应渲染模板（修复）

- 来源／实际场景：texmath_plugin循环内闭包捕获rule_block；eqno Token含eq1而HTML无编号。
- 原版现状：所有render_math_block闭包使用循环最后模板，编号模板丢失。
- 用户交付：为每条注册规则绑定自己的模板/渲染配置，编号和普通块分别输出。
- 影响模块：texmath/index.py:texmath_plugin渲染器工厂。
- 兼容边界：保持既有token类型和math内容；各delimiter对应模板只算该项矩阵。
- 正常验收：$$x$$ (eq1)输出eqno及eq1，普通$$x$$仍不造编号。
- 边界／错误验收：多个md实例/分隔配置、循环注册顺序、空编号策略和inline模板绑定回归。
- 原生回归：tests/test_texmath.py；tests/test_texmath fixtures。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 12．front matter点结束符正确终止（修复）

- 来源／实际场景：front_matter/index.py:_front_matter_rule；...被计content且EOF无匹配。
- 原版现状：检查上一行slice造成结束行错位，最后一行...不能关闭metadata。
- 用户交付：按当前扫描行识别结束符，排除delimiter本身，body第一行与EOF均处理正确。
- 影响模块：front_matter/index.py:_front_matter_rule。
- 兼容边界：保留---开闭与起始行规则；只修已经存在代码中的...关闭意图，不默认容忍任意未闭合输入。
- 正常验收：---/a:1/.../body内容仅a:1，body保留；EOF结束同样识别。
- 边界／错误验收：空metadata、连续点、带尾空格、嵌套位置、未闭合与map/hidden状态不误吞正文。
- 原生回归：tests/test_front_matter.py；tests/fixtures/front_matter.md。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 13．可配置front matter标记（增强）

- 来源／实际场景：[上游#134](https://github.com/executablebooks/mdit-py-plugins/issues/134)；+++ TOML当前只成段落。
- 原版现状：marker_chr硬编码-，调用签名无定制入口。
- 用户交付：允许配置明确的开启/关闭标记族，Token保留实际markup与格式提示。
- 影响模块：front_matter/index.py:插件配置/规则工厂。
- 兼容边界：默认YAML---保持；只抽取元数据不自动运行YAML/TOML/JSON解析器，未声明格式不猜测。
- 正常验收：+++包围内容可取出并保留正文，---默认输出不变。
- 边界／错误验收：marker长度/空字符/冲突、第一行限制、结束数量与未闭合回退明确。
- 原生回归：tests/test_front_matter.py。
- 实际功能依赖：12。

### 14．容器参数可解析结构化属性（增强）

- 来源／实际场景：[上游#129](https://github.com/executablebooks/mdit-py-plugins/issues/129)；speaker-name=Bob只留info。
- 原版现状：默认container只加name class，不解析附加属性。
- 用户交付：可选属性语法复用已有attrs解析/过滤规则，结构化放Token.attrs供render使用。
- 影响模块：container/index.py:container_plugin；attrs解析与策略复用。
- 兼容边界：默认参数作为原info保持；不采用issue里的未转义字符串拼HTML；属性允许列表明确。
- 正常验收：speaker容器输出speaker-name=Bob并正确转义属性值。
- 边界／错误验收：引号/空格值、class合并、保留name、拒绝onclick及自定义validate/render的交互清楚。
- 原生回归：tests/test_container.py；tests/test_attrs.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 15．锚点完成后提供标题回调（增强）

- 来源／实际场景：[上游#7](https://github.com/executablebooks/mdit-py-plugins/issues/7)；当前anchors签名无callback。
- 原版现状：slug_func只看到文字，拿不到去重后的真实slug/token/map。
- 用户交付：增加可选回调或env heading记录，在最终分配后传标题/slug/级别/map，便于导航。
- 影响模块：anchors/index.py:anchors_plugin/_make_anchors_func。
- 兼容边界：默认无副作用；parse再render不重复分配ID，不把permalink文本计入原标题。
- 正常验收：重复标题回调收到a和a-1，与HTML真实id一致。
- 边界／错误验收：过滤级别、自定义slug、callback报错策略、同md多次render与env复用不串文档。
- 原生回归：tests/test_anchors.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 16．锚点保留显式id并统一去重（增强）

- 来源／实际场景：attrs_block与anchors组合；{#custom}标题实际被覆盖成title。
- 原版现状：无选项保留调用方显式id，slugs集合只收自动生成值。
- 用户交付：新增显式id优先策略，先保留/登记现有id，再为缺失项分配不冲突slug。
- 影响模块：anchors/index.py:_make_anchors_func；attrs_block组合契约。
- 兼容边界：可保留原always overwrite模式；明确插件顺序和同名自定义id冲突，不静默改用户引用。
- 正常验收：显式custom保持，之后自动同名标题避开已占用id。
- 边界／错误验收：多个显式重复id、空id、Unicode、级别过滤、permalink与标题回调看见最终值。
- 原生回归：tests/test_anchors.py；tests/test_attrs.py。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 17．折叠提示可输出原生details结构（增强）

- 来源／实际场景：[上游#96](https://github.com/executablebooks/mdit-py-plugins/issues/96)；???+实际div/class。
- 原版现状：依赖外部脚本/CSS解释collapsible class，没有details/summary模式。
- 用户交付：增加可选details/summary渲染，???默认闭合、???+打开，保持标题行内解析。
- 影响模块：admon/index.py:规则token与render函数。
- 兼容边界：默认div/class保持；!!!普通提示不误变折叠，渲染器可自定义不依赖JS服务。
- 正常验收：浏览器原生结构字节可核对，???+有open，标题只出现一次。
- 边界／错误验收：无标题、嵌套提示/列表、标题HTML转义、自定义render和空内容结构合法。
- 原生回归：tests/test_admon.py；tests/test_admon fixtures。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 18．按来源base URL重写相对资源（增强）

- 来源／实际场景：[上游#113](https://github.com/executablebooks/mdit-py-plugins/issues/113)；相对链接/图片实际保持原值。
- 原版现状：使用方可以自写core规则，但无内置base URL插件。
- 用户交付：新增明确URL解析插件，对链接href/图片src应用配置或env来源base，供跨站预览。
- 影响模块：新增base URL插件；真实Token属性遍历。
- 兼容边界：不联网/下载资源；默认不启用，绝对URL、片段、mailto等按策略保留；保留normalize/validate。
- 正常验收：/docs和./images/x.png按指定文档base解析为正确绝对地址。
- 边界／错误验收：查询/片段、协议相对URL、反斜线、拒绝协议、嵌套图片/脚注与已有绝对URL不重复添加base。
- 原生回归：新增base URL回归；tests/test_footnote.py/属性组合。
- 实际功能依赖：无；不为填满顺序强造依赖。

### 19．项目issue和MR短引用链接（增强）

- 来源／实际场景：[上游#106](https://github.com/executablebooks/mdit-py-plugins/issues/106)；#123/!45目前文字。
- 原版现状：通用自动链接不识别仓库上下文短引用。
- 用户交付：新增可配置仓库短引用规则，GitHub issue和GitLab MR映射到明确配置URL。
- 影响模块：新增issue引用插件；行内Token规则。
- 兼容边界：不查询平台/发消息；代码、已有链接、转义和数字标题避免误触发，默认不启用。
- 正常验收：配置后正文#123/!45生成对应链接，`#99`保持代码。
- 边界／错误验收：跨仓格式是否支持明确，负值/零/紧邻单词、多个项目env与HTML属性中标记不误改。
- 原生回归：新增短引用fixtures；tests/test_gfm_autolink.py组合。
- 实际功能依赖：01, 09。

### 20．保留诗歌地址等行块布局（增强）

- 来源／实际场景：[上游#10](https://github.com/executablebooks/mdit-py-plugins/issues/10)、[Pandoc官方line blocks](https://pandoc.org/MANUAL.html#line-blocks)；管道开头多行目前普通段落。
- 原版现状：|文本行无法保留行块中的固定换行和行首空白。
- 用户交付：新增可选line block节点及HTML渲染，保留每行断行/缩进并支持声明的行内语法。
- 影响模块：新增line block插件；StateBlock行读取/Token.map。
- 兼容边界：默认CommonMark与table规则保持；不把所有含|的表格行误识别，不引入Pandoc运行依赖。
- 正常验收：三行诗歌/地址逐行输出，第二行额外缩进可保留。
- 边界／错误验收：空行/空块、长行续行、表格冲突、引用/列表内块、转义管道与source map明确。
- 原生回归：新增line block fixtures；表格/attrs/容器组合回归。
- 实际功能依赖：无；不为填满顺序强造依赖。

## 累计验收与不计步内容

已有脚注/内联脚注及docId前缀、定义列表、上下标、单行/块属性与allowed、容器/折叠class、Math多种分隔和renderer回调、front matter Token、字数env、MyST role/target/替换、GFM表格/删除线/任务/alerts。tasklists enabled=True已支持可点复选框，#59不能重复做一遍；anchors实体标题在当前核心text_join后正确，已实际排除错误怀疑。metadata可一次parse+renderer取得，不把#133文档说明或再次parse计增强；缺省数学HTML已经可由用户提供renderer，不声称新增一组delimiter就是独立能力。

每步在同一真实工作树累计修改，冻结独立验收由控制端保存，实际调用原生入口并核对模块来自候选源码。不得用候选删除 tests 或自报成功代替验收；默认离线使用预备的固定依赖，逐步回归此前全部已接受能力。文档、测试、兼容说明和失败重试属于各自交付，不拆成额外迭代。当前仅完成原版基线与研究，不宣称20项实现成功或已经上线。
