# python-frontmatter：二十步真实工程迭代路线

固定 [eyeseast/python-frontmatter@d2977d71638cb451bc06f2af3bb48e09e0dbe8c6](https://github.com/eyeseast/python-frontmatter/tree/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6)，原生证据见 [单仓审查](./python-frontmatter.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．元数据键不与Post构造参数冲突

- **来源／场景**：文档元数据本来就有content摘要字段或handler业务字段；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：loads把metadata通过**展开给Post(content,handler)，实测两个键分别触发multiple values TypeError；parse能读到字段却无法构成Post
- **交付及模块**：内部以显式metadata映射构建Post，保留既有公开构造调用并允许任意合法字符串字段；`frontmatter/__init__.py:loads`, `frontmatter/__init__.py:Post`。
- **兼容与实际依赖**：现有Post(content,handler,title=...)继续可用，元数据content不改变正文；不把两个键拆成两项；步骤依赖：无。
- **正常验收**：包含content/handler/title的YAML都能loads，正文和原handler对象独立保持
- **异常／边界验收**：空映射、None字段、同名默认值、非字符串键与自定义handler给出确定支持或类型错误
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 02．前导空白下格式识别和保存一致

- **来源／场景**：TOML文档前有空行，修改后要保持TOML格式；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：loads/checks在原文本detect，parse先strip再detect；实测metadata读取成功但Post.handler为None、checks为False且dumps改成YAML
- **交付及模块**：共享一次输入规范化及格式识别结果，使checks/parse/loads/load采用一致边界并保存实际handler；`frontmatter/__init__.py:detect_format`, `frontmatter/__init__.py:parse`, `frontmatter/__init__.py:loads`。
- **兼容与实际依赖**：保留默认parse接受前导空白的现行为；显式handler优先；空白保真属于独立opt-in模式；步骤依赖：无。
- **正常验收**：前导空行的TOML识别为TOMLHandler，检查为真且修改后仍+++输出
- **异常／边界验收**：前导缩进、CRLF、无metadata、格式不明与空文件一致；不隐式扩展README已要求显式处理的BOM策略
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 03．JSON导出结果可重新解析

- **来源／场景**：用户选择JSONHandler或indent=None生成文档；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/default_handlers.py)。
- **原版缺口**：JSONHandler只按单独一行花括号切分；实测空对象及compact导出都被当正文，合法列首嵌套结束括号又被提前截断
- **交付及模块**：以JSON解码器识别完整顶层对象结束位置，保证内建JSON export选项的往返一致；`frontmatter/default_handlers.py:JSONHandler`。
- **兼容与实际依赖**：保留原多行JSON格式和后续正文；只消费首个完整对象，不把正文花括号误当metadata；不把空/compact/嵌套拆项；步骤依赖：无。
- **正常验收**：空对象、compact与嵌套metadata的dumps/loads保留字典和正文
- **异常／边界验收**：JSON字符串内括号/转义、空白分隔、坏JSON、非对象根与正文以大括号开头都有明确边界
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 04．区分缺少、无效和非映射元数据

- **来源／场景**：编辑器要判断文档没有Front Matter还是作者写错结构；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：parse遇split ValueError回退全文，非dict YAML结果静默忽略；checks仅看开头delimiter，无法说明解析状态
- **交付及模块**：新增ParseResult与可选严格策略，区分absent/present/malformed/non_mapping并保留原段和诊断；`frontmatter/__init__.py:parse`, `frontmatter/__init__.py:checks`, `frontmatter/default_handlers.py:BaseHandler`。
- **兼容与实际依赖**：原宽容parse返回合同保持；strict显式启用，不把所有普通正文开头横线自动判错；步骤依赖：无。
- **正常验收**：合法空metadata为present，缺header为absent，列表根及未闭合边界可被清楚区分
- **异常／边界验收**：显式custom handler、空YAML、只有分隔符、坏格式及handler异常不被混为缺元数据
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 05．正文空白和行结束策略

- **来源／场景**：代码片段或诗歌文档需要保留首尾缩进和末尾空行；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/util.py)。
- **原版缺口**：u把CRLF换LF，parse及BaseHandler.format两处strip；实测无metadata文本的前导两个空格和末尾空行丢失
- **交付及模块**：新增显式ContentWhitespacePolicy，控制剥离、原样正文与换行保留，并记录输入格式；`frontmatter/util.py:u`, `frontmatter/__init__.py:parse`, `frontmatter/default_handlers.py:BaseHandler.format`。
- **兼容与实际依赖**：默认原strip/规范换行行为不变；不把有意历史行为称缺陷；正文策略与metadata格式化分开；步骤依赖：无。
- **正常验收**：原样模式读取/导出缩进诗歌和空行逐字符一致，默认输出与原版相同
- **异常／边界验收**：仅空白正文、CRLF/LF混用、无末尾换行、首行缩进和delimiter附近空白有清楚规则
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 06．可选YAML编辑样式保留

- **来源／场景**：校订标题时希望保留编辑注释、引号与键顺序；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/default_handlers.py)。
- **原版缺口**：PyYAML loader转普通dict，导出会丢注释/引号风格；已有pyaml美化及sorted handler示例仅改变输出样式
- **交付及模块**：增加可选roundtrip YAML handler，保留解析文档节点及字段编辑痕迹；`frontmatter/default_handlers.py:YAMLHandler`, `frontmatter/__init__.py:Post`, `examples/sorted.py`。
- **兼容与实际依赖**：不重计现有custom handler/pretty dump；依赖可选且默认PyYAML不变，不能表达时标明重建范围；步骤依赖：无。
- **正常验收**：只改title时注释与未改字段风格保持，新增键遵循显式插入策略
- **异常／边界验收**：锚点/引用、块标量、合并键、重复键和整体替换metadata有确定保留或规范化说明
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 07．字段和正文到原文件的位置

- **来源／场景**：编辑器需要把坏日期或title字段定位到完整文档；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：handler解析器可能带metadata内部行号，但Post不保存起止段或字段到原文件映射
- **交付及模块**：新增parse_with_locations，记录header边界、字段位置、正文起点及结构化诊断；`frontmatter/__init__.py:parse`, `frontmatter/default_handlers.py:BaseHandler`, `frontmatter/util.py:u`。
- **兼容与实际依赖**：保留默认轻量返回；字节/字符/行列坐标区分，第三方handler可声明无字段级位置；步骤依赖：无。
- **正常验收**：YAML/TOML/JSON已知字段位置能定位原行，正文offset包含真实分隔符长度
- **异常／边界验收**：前导空白、CRLF、UTF8多字节、跨行标量和重复键不使用错误的一一对应位置
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 08．可复用的文档元数据合同

- **来源／场景**：栏目要求title字符串、tags列表和published日期，入库前需统一核验；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：Post只是字典代理，PyYAML类型转换不等于业务schema；原版无聚合字段验证合同
- **交付及模块**：新增可选MetadataSchema验证入口，支持必填、类型、枚举、未知字段和自定义诊断；`frontmatter/__init__.py:Post`, `frontmatter/default_handlers.py:YAMLHandler`。
- **兼容与实际依赖**：原读取不强制某套schema，不把所有日期字符串悄悄转date；验证默认只返回报告；步骤依赖：无。
- **正常验收**：符合栏目合同的中文文档通过，多个缺字段/类型错误一次列出路径
- **异常／边界验收**：嵌套对象、None与缺失、bool/数字区别、异构列表及未知扩展字段由明确规则决定
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 09．嵌套字段的精确更新

- **来源／场景**：编辑器要只改seo.image.url而保留seo其他资料；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：Post只代理顶层__getitem__/__setitem__，调用方自行遍历嵌套字典/数组；无明确路径语法与变更合同
- **交付及模块**：新增metadata path get/set/delete及编辑计划，明确定义转义键、列表索引和缺路径策略；`frontmatter/__init__.py:Post`。
- **兼容与实际依赖**：不改变原字典访问；字面点号键必须可转义，不把任意点号都自动解释成嵌套；步骤依赖：无。
- **正常验收**：更新嵌套URL只改目标，返回可核对原值/新值，顶层访问保持
- **异常／边界验收**：点号/斜杠键、负索引、越界、途中标量、缺路径创建和空路径均有确定错误或显式选项
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 10．分层默认值的合并与来源

- **来源／场景**：站点默认、栏目默认与单文档metadata需要合并但保留未覆盖嵌套值；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：parse的defaults.copy加metadata.update是浅层覆盖；实测settings.theme覆盖同时丢默认lang
- **交付及模块**：新增显式merge_metadata profile，控制深层字典、列表替换/追加、删除标记和字段来源；`frontmatter/__init__.py:parse`, `frontmatter/__init__.py:Post`。
- **兼容与实际依赖**：默认浅覆盖保持；不默认拼接所有列表，合并过程不修改调用方默认对象；步骤依赖：无。
- **正常验收**：站点lang与文档theme同时保留，每字段能说明来自哪一层
- **异常／边界验收**：None/缺失区别、字典变标量、重复列表、冲突层顺序和循环Python对象有清楚边界
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 11．按版本迁移文档元数据

- **来源／场景**：栏目把author字段改为authors列表并升级schema版本；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：可手工读改字典，但无有序迁移、已迁状态、失败回滚或迁移报告合同
- **交付及模块**：新增版本化metadata migration计划，注册显式字段/值转换并先预览后应用；`frontmatter/__init__.py:Post`, `frontmatter/__init__.py:load`, `frontmatter/__init__.py:dump`。
- **兼容与实际依赖**：仅执行调用方提供的本地迁移，不从文档加载可执行代码；正文保持，未知版本不猜测；步骤依赖：无。
- **正常验收**：v1 author迁到v2 authors并记录变更，再迁移幂等，失败不半改Post
- **异常／边界验收**：缺版本、跨多版本、已占目标键、部分字段失败和不支持逆迁移有明确结果
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 12．跨格式转换的类型保真报告

- **来源／场景**：把YAML元数据导成JSON/TOML时希望先知道日期等类型如何处理；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/default_handlers.py)。
- **原版缺口**：显式切handler已支持转换，但YAML日期对象到JSON实测TypeError；不同格式类型交集与有损规则无报告
- **交付及模块**：新增conversion_plan，预检目标可表达类型并允许显式日期/特殊数值等转换策略；`frontmatter/default_handlers.py:YAMLHandler`, `frontmatter/default_handlers.py:JSONHandler`, `frontmatter/default_handlers.py:TOMLHandler`。
- **兼容与实际依赖**：不把已有切handler说成新格式支持；默认不擅自str所有未知对象，失败仍可保持原文；步骤依赖：无。
- **正常验收**：普通字典三格式保持同值，YAML date按所选ISO字符串策略转换且报告类型变化
- **异常／边界验收**：None与TOML、datetime时区、NaN、非字符串键、集合及自定义对象给出逐路径支持/拒绝理由
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 13．显式编码的字节流读写

- **来源／场景**：资料工具拿到BytesIO，希望按选定编码读写完整文档；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：loads(bytes)已有解码，但load先detect_format对BytesIO.read返回bytes做str正则报错；dump直接往二进制流write字符串也报错，bytes(Post)仅是正文
- **交付及模块**：新增明确binary input/output合同与完整文档bytes入口，统一解码、编码及BOM策略；`frontmatter/__init__.py:load`, `frontmatter/__init__.py:dump`, `frontmatter/util.py:u`。
- **兼容与实际依赖**：原TextIO、文件路径与loads(bytes)保持；不改变bytes(Post)现有仅正文语义；调用方流不擅自关闭；步骤依赖：无。
- **正常验收**：BytesIO中的UTF8中文metadata/正文可完整读写，UTF8-sig通过显式策略识别
- **异常／边界验收**：UTF16/32、空流、半字节、非法编码、文本/二进制写入器不匹配和当前位置处理都有清楚结果
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 14．只读取文档头部的流式入口

- **来源／场景**：大文档只要metadata，正文需要交给其他流式消费者；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：load/check对fd一次read全部内容；handler.split基于完整文本，不能返回未消费正文流
- **交付及模块**：新增read_frontmatter，逐块识别头部并返回metadata及保留已缓冲字节的正文读取器；`frontmatter/__init__.py:load`, `frontmatter/default_handlers.py:BaseHandler.split`, `frontmatter/util.py`。
- **兼容与实际依赖**：默认load仍完整返回Post；JSON采用完整对象边界，custom handler需声明流能力；不丢失预读正文；步骤依赖：无。
- **正常验收**：大正文读取metadata后仍可从body reader读全正文，结果与完整parse一致
- **异常／边界验收**：UTF8/CRLF/分隔符跨块、无Front Matter、未闭合头部和消费者提前关闭遵循流所有权合同
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 15．每次调用独立的格式注册表

- **来源／场景**：同一进程有普通Markdown和Pandoc文档，不能相互改全局handlers；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：BaseHandler可扩展，detect_format已接受handlers参数，但load/loads/checks使用模块全局列表或单一handler
- **交付及模块**：新增HandlerRegistry并允许每次解析/检查/导出注入，明确匹配顺序、格式名和冲突报告；`frontmatter/__init__.py:handlers`, `frontmatter/__init__.py:detect_format`, `frontmatter/default_handlers.py:BaseHandler`, `examples/pandoc.py`。
- **兼容与实际依赖**：不重计自定义handler已有能力；默认全局顺序保持，不自动启用可选TOML依赖；步骤依赖：无。
- **正常验收**：普通与Pandoc注册表并行使用各自结束符，返回稳定格式标识供再次导出
- **异常／边界验收**：多个handler匹配、缺依赖、同名注册、无匹配与显式handler覆盖顺序都有确定行为
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 16．结构化的Post快照与交换

- **来源／场景**：数据管线要把正文、metadata及来源格式分别存成一条记录；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：to_dict把metadata平铺后写content；实测metadata已有content会被覆盖，嵌套值也仅浅复制；这是既有扁平合同
- **交付及模块**：新增版本化envelope/snapshot，独立content/metadata/format/provenance并显式序列化扩展类型；`frontmatter/__init__.py:Post.to_dict`, `frontmatter/__init__.py:Post`。
- **兼容与实际依赖**：原to_dict与str/bytes保持；新结构不因metadata字段名冲突丢值，不把handler实例直接JSON化；步骤依赖：无。
- **正常验收**：含metadata.content与正文同时往返，快照修改嵌套字典不影响原Post，格式标识可核对
- **异常／边界验收**：未知handler、日期等非JSON类型、schema版本不符和不可复制对象可明确拒绝或用已注册codec
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 17．预检后的原子文件更新

- **来源／场景**：批量校订标题时文件可能被编辑器同时改动，失败不能留下半截文档；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：dump(path)直接以w打开写出，没有内容预期值检查、临时写替换及权限/换行策略合同
- **交付及模块**：新增update_file，先解析与变更预览，再验证原文件摘要并同目录临时写/替换；`frontmatter/__init__.py:dump`, `frontmatter/__init__.py:load`, `frontmatter/__init__.py:dumps`。
- **兼容与实际依赖**：原dump简单行为保持；默认不覆盖并发新内容，明确符号链接和文件权限处理；变更函数失败不写盘；步骤依赖：无。
- **正常验收**：单字段更新成功保留正文与目标权限，预览可核对，内容未变可不写
- **异常／边界验收**：并发修改、序列化错误、磁盘写失败、replace失败、无metadata文件和外部流输出各有确定结果
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 18．带标识的多文档处理

- **来源／场景**：资料导入接收一串文档记录，需要保留id与局部失败；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：现有load/loads一次处理一个输入，无统一有序结果/按条错误/统计合同
- **交付及模块**：新增load_records或transform_records，接收带id来源并产生成功/失败结果与解析格式；`frontmatter/__init__.py:load`, `frontmatter/__init__.py:loads`, `frontmatter/__init__.py:Post`。
- **兼容与实际依赖**：不自动吞未知系统异常，continue/fail-fast明确；不把每记录重试/测试另算交付；步骤依赖：无。
- **正常验收**：三条资料中一条坏YAML按策略单独失败，其他保留id/顺序与完整内容
- **异常／边界验收**：重复id、懒生成器抛错、空记录、输入流重用和消费者中断有准确已完成/未执行状态
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 19．可查询的本地文档目录

- **来源／场景**：编辑者要找指定标签、发布日期范围和未校对的本地资料；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/frontmatter/__init__.py)。
- **原版缺口**：单文档解析不提供可复用目录、字段投影或变更刷新；手工glob加列表过滤分散处理
- **交付及模块**：新增DocumentCatalog，维护路径/摘要/格式/字段投影索引并按明确类型谓词查询；`frontmatter/__init__.py:load`, `frontmatter/__init__.py:Post`, `frontmatter/__init__.py:checks`。
- **兼容与实际依赖**：只索引本地明确目录，不自动渲染正文或调用网络；schema缺失类型以未知返回，不静默字符串比较日期；步骤依赖：无。
- **正常验收**：按tag和status查询中文资料正确，增删改文件刷新只更新受影响条目
- **异常／边界验收**：重名、坏文档、日期类型混用、字段缺失、路径排除和文件刷新中变化都保留诊断
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。

## 20．本地文档元数据命令入口

- **来源／场景**：资料维护者不用Python脚本就想查看、验证与预览修改；[固定源码](https://github.com/eyeseast/python-frontmatter/blob/d2977d71638cb451bc06f2af3bb48e09e0dbe8c6/pyproject.toml)。
- **原版缺口**：pyproject无console script，现有examples是handler扩展示例及测试生成工具
- **交付及模块**：新增CLI inspect/check/convert/update-preview，明确输入格式、字段投影和机器JSON结果；`pyproject.toml`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`。
- **兼容与实际依赖**：默认只读或预览，写文件必须显式命令选项；复用库策略，不另写一套格式解析；步骤依赖：无。
- **正常验收**：读取中文Markdown输出metadata，显式转换可预检类型，未知字段/格式有清楚退出码
- **异常／边界验收**：标准输入、空文件、坏metadata、可选TOML缺失、输出重名和部分文件失败不混成成功
- **原生回归**：`tests/unit_test.py`, `tests/test_files.py`, `tests/test_docs.py`, `frontmatter/__init__.py`, `frontmatter/default_handlers.py`, `examples/pandoc.py`, `examples/reversed.py`, `README.md`。
