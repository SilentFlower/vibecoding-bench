# TOMLKit：二十步真实工程迭代路线

固定 [python-poetry/tomlkit@eddd27e43a62fe58707c311bfad2f52e72493f53](https://github.com/python-poetry/tomlkit/tree/eddd27e43a62fe58707c311bfad2f52e72493f53)，原生证据见 [单仓审查](./tomlkit.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．删除 inline 点分字段后保持合法结构

- **类型与来源**：修复；[官方 #662](https://github.com/python-poetry/tomlkit/issues/662) 与固定源码。
- **原版现状与收益**：删除 b.c 的 c 后实际 t={a="", ,d=1}，Python逻辑仍含 b={}。
- **交付及模块**：修正 inline table 的片段删除和分隔符，并按逻辑保留明确空表；items.py:InlineTable、container.py:remove／__delitem__。
- **兼容与依赖**：不以删除整个 b 偷换成清理空表策略；正常字段顺序与空白保持；步骤依赖：无。
- **正常验收**：首中尾位置删最后子字段后标准库能解析且与 unwrap一致。
- **异常／边界验收**：单字段、多级点分、注释和空 inline table，连续删／加均有效。
- **原生回归**：tests/test_items.py、tests/test_write.py、tests/test_toml_document.py。

## 02．不连续表代理正确解析和解包

- **类型与来源**：修复；[官方 #661](https://github.com/python-poetry/tomlkit/issues/661) 与固定源码、#632、#577。
- **原版现状与收益**：深层缩进表、点分后置父表、AoT 后置子表分别 ParseError或KeyAlreadyPresent，均已对照标准库。
- **交付及模块**：统一 OutOfOrderTableProxy 的父片段合并及Trivia访问，parse、索引和unwrap一致；parser.py:_parse_table、container.py:OutOfOrderTableProxy。
- **兼容与依赖**：只合并 TOML 允许扩展的片段，真实重复具体表仍拒绝；三个症状合为一步；步骤依赖：无。
- **正常验收**：三个实测文档可往返，unwrap与tomllib等价。
- **异常／边界验收**：缩进0..多层、相邻／分隔片段、AoT元素归属、真正类型冲突不放过。
- **原生回归**：tests/test_parser.py、tests/test_toml_tests.py、tests/test_toml_document.py。

## 03．数组原位重复同步序列化

- **类型与来源**：修复；[官方 #646](https://github.com/python-poetry/tomlkit/issues/646) 与固定源码。
- **原版现状与收益**：绑定数组 *=2 的列表值变4项而输出仍2项。
- **交付及模块**：实现Array原位重复，复用完整索引／body同步通道，保留对象身份；items.py:Array.__imul__／clear／extend。
- **兼容与依赖**：遵守Python list重复次数语义；不是把 *= 改成返回脱离文档的新对象；步骤依赖：无。
- **正常验收**：*=0／1／2 后 list、dumps、重新parse语义一致，后续append继续正确。
- **异常／边界验收**：负次数、bool／非法类型、含注释多行数组和自引用拒绝边界。
- **原生回归**：tests/test_items.py、tests/test_write.py。

## 04．表结构替换保持完整父路径和兄弟归属

- **类型与来源**：修复；[官方 #557](https://github.com/python-poetry/tomlkit/issues/557) 与固定源码、#556。
- **原版现状与收益**：实测[t] a.b 后添加 a.c 输出顶层[a.c]；scalar改table使a.c/a.d被捕获。
- **交付及模块**：结构替换按完整路径重排相关片段，保留兄弟键真实归属；container.py:_replace_at／append、items.py:Table。
- **兼容与依赖**：不简单字符串替换表名；原逻辑树是裁判，格式仅在必要局部调整；步骤依赖：无。
- **正常验收**：两种实测修改的标准库重解析与doc.unwrap完全一致。
- **异常／边界验收**：多级点分、表数组、前后兄弟、注释、空表和重复更改后不漂移。
- **原生回归**：tests/test_toml_document.py、tests/test_write.py、tests/test_parser.py。

## 05．修改后空容器可序列化

- **类型与来源**：修复；[官方 #553](https://github.com/python-poetry/tomlkit/issues/553) 与固定源码。
- **原版现状与收益**：删除x.y.z最后键后logical含x.y={}但dumps只保留a=[]；空虚拟节消失。
- **交付及模块**：给被显式修改后仍存在的空表提供合法表示，空AoT变普通空数组的既有修复回归；container.py、items.py:Table／AoT。
- **兼容与依赖**：无修改原文不凭空增加隐式父表；区分保留空容器与显式删除键；步骤依赖：无。
- **正常验收**：示例空x.y和a同时写回，语义与unwrap一致。
- **异常／边界验收**：顶层／嵌套空表、最后AoT元素、inline table和先删后加不丢节点。
- **原生回归**：tests/test_write.py、tests/test_items.py、tests/test_toml_document.py。

## 06．显式排序递归作用于解析文档

- **类型与来源**：修复；[官方 #614](https://github.com/python-poetry/tomlkit/issues/614) 与固定源码。
- **原版现状与收益**：parsed Table 已是Item，item直接返回；sort_keys只重建顶层，子表原序保留。
- **交付及模块**：递归排序解析后的Table／InlineTable／AoT内键，保留值类型和可归属注释；api.py:dumps、items.py:item、container.py。
- **兼容与依赖**：sort_keys=False仍完全保真；显式排序会移动相关格式，不能承诺原始字节不变；步骤依赖：无。
- **正常验收**：parsed与plain mapping的嵌套键排序一致，AoT元素顺序保持。
- **异常／边界验收**：点分虚拟表、重复片段、Unicode键、comments、数组内dict不被当普通表逃逸。
- **原生回归**：tests/test_write.py、tests/test_build.py、tests/test_items.py。

## 07．替换字符串时可保留引号风格

- **类型与来源**：增强；[官方 #325](https://github.com/python-poetry/tomlkit/issues/325) 与固定源码。
- **原版现状与收益**：把单引号字符串赋新str实测改为双引号，需手工重建String。
- **交付及模块**：提供preserve_style的值替换便利入口，沿用可表示的原StringType；container.py:_replace、items.py:String。
- **兼容与依赖**：默认普通赋值策略保持；新值不能用旧引号表示时明确fallback或报错；步骤依赖：无。
- **正常验收**：单引号／双引号／多行字符串在安全范围内替换仍保持原风格。
- **异常／边界验收**：内含原delimiter、换行、控制字符和反斜杠按TOML合法性决策，不输出无效文本。
- **原生回归**：tests/test_items.py、tests/test_toml_document.py。

## 08．原始多行字符串的首换行策略

- **类型与来源**：增强；[官方 #655](https://github.com/python-poetry/tomlkit/issues/655) 与固定源码。
- **原版现状与收益**：string(multiline,literal,escape=False) 的首换行行为变动缺少显式选择，路线不未经定义判BUG。
- **交付及模块**：提供显式leading_newline=preserve／trim_delimiter，区分原始语法输入与语义值；api.py:string、items.py:String.from_raw。
- **兼容与依赖**：原默认沿用，不能为去视觉空行而改变实际字符串；新增选项清楚命名；步骤依赖：无。
- **正常验收**：含首换行的输入在指定语义下dump→stdlib读回预期字符串。
- **异常／边界验收**：一个／多个首换行、空字符串、尾换行、literal/basic与escape组合全部明确。
- **原生回归**：tests/test_build.py、tests/test_items.py、tests/test_write.py。

## 09．批量生成文档的数组布局策略

- **类型与来源**：增强；[官方 #385](https://github.com/python-poetry/tomlkit/issues/385) 与固定源码、#290。
- **原版现状与收益**：每个Array可手动multiline和add_line，但dumps无整文档的长度／项目数／缩进策略。
- **交付及模块**：新增显式render policy，控制新数组多行阈值、最大行宽及层级缩进；api.py:dumps、items.py:Array 渲染。
- **兼容与依赖**：默认解析文档保真；只显式reformat或新建节点应用，不能重排已有注释；步骤依赖：无。
- **正常验收**：小数组单行、大数组多行，嵌套层级缩进一致。
- **异常／边界验收**：超长单字符串、空数组、带comments和inline table在当前TOML规范下合法。
- **原生回归**：tests/test_write.py、tests/test_build.py、tests/test_items.py。

## 10．可选输出隐式父表标题

- **类型与来源**：增强；[官方 #447](https://github.com/python-poetry/tomlkit/issues/447) 与固定源码。
- **原版现状与收益**：默认plain nested dict跳过无值的父table标题，用户需逐层手工table(False)。
- **交付及模块**：增加emit_parent_headers选项用于新生成文档，保留清晰层次；api.py:dumps、items.py:Table、container.py 渲染。
- **兼容与依赖**：默认紧凑标题保持；只显式启用后产生额外合法父节，语义不变；步骤依赖：无。
- **正常验收**：apps/test/子报表生成每层父标题且标准库值一致。
- **异常／边界验收**：重复隐式父表、空表、AoT与缩进不违反重复定义规则。
- **原生回归**：tests/test_write.py、tests/test_build.py。

## 11．解析节点保留源区间

- **类型与来源**：增强；[官方 #55](https://github.com/python-poetry/tomlkit/issues/55) 与固定源码。
- **原版现状与收益**：ParseError有位置，普通Item／Key没有公开源区间。
- **交付及模块**：在parse可选track_positions模式记录字节／字符偏移和行列，公开只读SourceSpan；parser.py、source.py、items.py:Item／Key。
- **兼容与依赖**：默认保真结构保持；修改后的节点标记synthetic或过期，不猜新文件位置；步骤依赖：无。
- **正常验收**：键／值／table标题定位对应原始切片，多行正确。
- **异常／边界验收**：Unicode字节与字符坐标区分、CRLF、空节点与修改后span状态明确。
- **原生回归**：tests/test_parser.py、tests/test_utils.py（新增源区间用例放入现有集合）。

## 12．按TOML键路径查询与修改

- **类型与来源**：增强；[官方 #133](https://github.com/python-poetry/tomlkit/issues/133) 与固定源码。
- **原版现状与收益**：没有get_path/set_path便利API，普通字典索引可用但调用者易拆错带点引号键。
- **交付及模块**：新增键路径解析与get/set/delete，复用TOML Key语法，首版不支持任意jsonpath表达式；api.py:key、container.py、路径helper。
- **兼容与依赖**：普通字符串键仍字面；新入口显式区分路径，绝不eval；步骤依赖：无。
- **正常验收**：含plugins."io.containerd.grpc.v1.cri"的路径定位并修改正确节点。
- **异常／边界验收**：缺父节、scalar阻挡、空键、引号转义、AoT索引范围和不存在路径策略。
- **原生回归**：tests/test_toml_document.py、tests/test_parser.py。

## 13．公开有序插入和移动条目

- **类型与来源**：增强；[官方 #7](https://github.com/python-poetry/tomlkit/issues/7) 与固定源码。
- **原版现状与收益**：Container有私有_insert_at，公开文档只有add/append；数组insert不等于文档insert。
- **交付及模块**：提供insert_before/after与move，按键位置移动完整条目及明确归属的Trivia；container.py、TOMLDocument。
- **兼容与依赖**：保持append API，不暴露body内部数字下标；不能拆开合法表范围；步骤依赖：无。
- **正常验收**：把metadata表插到最前，注释和已有数据均保持。
- **异常／边界验收**：目标不存在、自己前后移动、空文档、点分key和AoT边界；重复键拒绝。
- **原生回归**：tests/test_toml_document.py、tests/test_write.py。

## 14．带注释的键重命名

- **类型与来源**：增强；固定源码和配置编辑实际场景分析（增强提案）。
- **原版现状与收益**：公开删除再添加会改变顺序／引号／注释，_replace为私有手段。
- **交付及模块**：新增rename_key在所属容器保留位置和Trivia，并检查目标冲突；container.py:_replace、items.py:AbstractTable。
- **兼容与依赖**：旧dict赋值行为保持；首版重命名单个键，不隐式改其他字符串引用；步骤依赖：无。
- **正常验收**：foo→bar后位置／inline注释保持，值类型保持。
- **异常／边界验收**：目标存在时原文不变，点分键与quoted key明确；父表名变更后全路径保持。
- **原生回归**：tests/test_toml_document.py、tests/test_items.py。

## 15．显式文档递归合并策略

- **类型与来源**：增强；[官方 #37](https://github.com/python-poetry/tomlkit/issues/37) 与固定源码 的配置层叠使用场景；非重复原有table解析修复。
- **原版现状与收益**：update是映射更新，缺少冲突／数组策略明确且保留现有样式的深合并入口。
- **交付及模块**：新增merge_document，提供 scalar冲突、list替换／追加、comment来源策略；container.py、items.py:Table／AoT。
- **兼容与依赖**：默认update保持；不把重复表解析容错当深合并，避免共用隐式规则；步骤依赖：无。
- **正常验收**：base与overlay只改目标字段，未触及comment／值格式保持。
- **异常／边界验收**：table与scalar冲突、AoT无主键默认整体替换、嵌套失败整体回滚。
- **原生回归**：tests/test_toml_document.py、tests/test_write.py。

## 16．TOML文件原子写入

- **类型与来源**：增强；toml_file.py:TOMLFile.write 直接文本w打开目标。
- **原版现状与收益**：序列化完成后写盘失败仍可能截断旧文件。
- **交付及模块**：提供atomic=True同目录临时发布与模式保留，沿用_linesep转换；toml_file.py:TOMLFile.write。
- **兼容与依赖**：原write默认保持；不把原子replace说成断电持久化，symlink行为明确；步骤依赖：无。
- **正常验收**：LF／CRLF／mixed三类正常更新后字节与策略一致。
- **异常／边界验收**：编码、写盘、replace失败不破坏旧内容，清理临时文件；权限不可静默放宽。
- **原生回归**：tests/test_toml_file.py。

## 17．拒绝陈旧文件编辑覆盖

- **类型与来源**：增强；TOMLFile.read/write 无摘要或版本条件；原生文件编辑协作场景。
- **原版现状与收益**：read后外部修改，write会覆盖新内容而不提示。
- **交付及模块**：可选expected_digest和合作写锁覆盖读改写提交检查，返回明确冲突；toml_file.py:TOMLFile。
- **兼容与依赖**：普通write保留；只承诺合作本地写入者，不声称阻止任意编辑器竞争；步骤依赖：16。
- **正常验收**：A读后B改，A条件写被拒且B字节完整；重读后更新可成功。
- **异常／边界验收**：文件删除／替换、相同字节不同mtime、锁失败及异常释放；与原子发布组合。
- **原生回归**：tests/test_toml_file.py。

## 18．多项编辑的事务补丁

- **类型与来源**：增强；固定源码和配置编辑实际场景分析（增强提案）。
- **原版现状与收益**：调用者逐次变更时后一步失败会留下前半修改，没有公开批量事务契约。
- **交付及模块**：提供有界patch集合test/set/delete/rename，预检并在副本完整应用后接受；文档patch helper、container.py。
- **兼容与依赖**：不暗中写文件；仅显式patch入口一次成功或保持原文，普通赋值不变；步骤依赖：12、14。
- **正常验收**：多处修改成功后一次导出，失败test使原doc.as_string逐字不变。
- **异常／边界验收**：重复目标、路径越界、AoT索引移动、操作数上限和自引用值拒绝。
- **原生回归**：tests/test_toml_document.py、tests/test_write.py。

## 19．文档范围的自定义编码器

- **类型与来源**：增强；api.py:register_encoder／items.py:CUSTOM_ENCODERS 实际全局列表。
- **原版现状与收益**：现有注册全局影响其他调用，宿主多文档使用不同类型规则困难。
- **交付及模块**：dumps/item提供显式encoder集合或作用域上下文，递归调用沿同一集合；api.py:dumps／register_encoder、items.py:item。
- **兼容与依赖**：全局注册API保留作为默认后备；显式集合隔离，线程与嵌套不靠临时改全局；步骤依赖：无。
- **正常验收**：同一自定义类型在两组dump各用自己的表示，全局列表不被写入。
- **异常／边界验收**：编码器拒绝／递归产生未知类型／抛错时有限失败，原生Item保真和排序透传。
- **原生回归**：tests/test_api.py、tests/test_build.py、tests/test_items.py。

## 20．配置的语义差异报告

- **类型与来源**：增强；固定源码和配置编辑实际场景分析（增强提案）。
- **原版现状与收益**：可dump字符串但没有忽略排版比较两份配置的公开差异结果。
- **交付及模块**：提供semantic_diff列新增／删除／变更的键路径与类型，可选另列样式变化；文档diff helper、Item.unwrap／Key。
- **兼容与依赖**：不自动应用补丁；默认诊断不暴露值，可显式允许本地显示；步骤依赖：无。
- **正常验收**：只改注释的两份配置语义差异为空，实际端口变化定位server.port。
- **异常／边界验收**：NaN比较、日期类型、AoT位置语义、带点引号键和大文档有界输出。
- **原生回归**：tests/test_toml_document.py、tests/test_items.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
