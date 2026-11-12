# feedgen：二十步真实工程迭代路线

固定 [lkiesow/python-feedgen@97260abb1793eb164c458c10b493690beb413f6d](https://github.com/lkiesow/python-feedgen/tree/97260abb1793eb164c458c10b493690beb413f6d)，原生证据见 [单仓审查](./feedgen.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．Atom条目链接属性保留

- **来源／场景**：条目链接设置rel/type/hreflang/title/length后应出现在输出；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/entry.py)。
- **原版缺口**：atom_entry循环把link字典变量覆盖成XML元素，再用元素get读取尚未写入的属性；实测只保留href
- **交付及模块**：修正单一序列化错误，完整保留所有已公开支持的链接元数据；`feedgen/entry.py:FeedEntry.atom_entry`。
- **兼容与实际依赖**：这是同一根因的一项修复，不把五个属性拆数；feed层和RSS映射保持；步骤依赖：无。
- **正常验收**：alternate/enclosure链接输出完整属性，enclosure的MIME与长度可读
- **异常／边界验收**：属性缺失、空值、多个链接、零长度和Unicode标题分别保持明确语义
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 02．Atom内嵌二进制内容

- **来源／场景**：本地订阅需要携带小段非文本内容；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/entry.py)。
- **原版缺口**：_add_text_elm对非text/XML类型明确NotImplementedError；content src是现有外部引用替代
- **交付及模块**：新增显式bytes内容接口，按Atom内容类型进行base64编码并序列化；`feedgen/entry.py:_add_text_elm`, `feedgen/entry.py:FeedEntry.content`。
- **兼容与实际依赖**：文本/html/xhtml/XML入口不变；不把已编码字符串自动再编码；限制内嵌大小；步骤依赖：无。
- **正常验收**：给已知bytes与MIME类型，解析base64可逐字节恢复原内容
- **异常／边界验收**：空bytes、未知type、同时src与inline、大小超限和不合法输入类型明确失败
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 03．导出前统一验证报告

- **来源／场景**：批量生成需一次知道feed与所有entry缺哪些字段；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/util.py)。
- **原版缺口**：setter有ensure_format，_create_atom/rss及entry导出首次遇错抛ValueError；无validate报告
- **交付及模块**：新增按输出格式检查的结构化报告，含字段路径、条目ID和严重程度；`feedgen/util.py:ensure_format`, `feedgen/feed.py:_create_atom`, `feedgen/entry.py:FeedEntry.atom_entry`。
- **兼容与实际依赖**：保留现有异常入口；未生成XML不自称格式验证通过；不修改builder数据；步骤依赖：无。
- **正常验收**：多个条目分别缺title/id时一次返回各自路径，合法feed无错误
- **异常／边界验收**：Atom/RSS不同必填项、日期无时区、类型错、扩展错误与缺作者继承均明确
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 04．JSON Feed输出

- **来源／场景**：文档订阅需要与JSON Feed客户端交换；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：公开仅RSS/Atom，原生CLI是固定测试feed演示，无jsonfeed_str
- **交付及模块**：增加JSON Feed1.1输出适配，明确作者、正文、附件与日期映射及损失报告；`feedgen/feed.py:FeedGenerator`, `feedgen/entry.py:FeedEntry`。
- **兼容与实际依赖**：不把RSS扩展字段静默丢失；缺映射字段保留明确扩展区或报告；步骤依赖：无。
- **正常验收**：简单文档feed导出后id/title/content及两作者顺序正确
- **异常／边界验收**：只有HTML/只有text、无URL项目、多附件、重复ID和无法表达的扩展有边界
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 05．Atom删除记录

- **来源／场景**：归档订阅需要告知客户端一条已发布记录被移除；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：remove_entry仅从当前列表删除，不输出删除事件；无tombstone扩展
- **交付及模块**：增加明确删除记录模型与Atom扩展输出，记录ref、when和可选原因；`feedgen/feed.py:FeedGenerator.remove_entry`, `feedgen/ext/base.py`。
- **兼容与实际依赖**：默认移除行为保持；删除事件与普通entry分开；不执行客户端操作；步骤依赖：无。
- **正常验收**：指定已知ID的删除记录在输出中保留引用和时刻，正常entry不受影响
- **异常／边界验收**：未知ID、重复事件、naive时间、同ID新旧记录及RSS无对应语义有明确策略
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 06．Atom讨论关系

- **来源／场景**：订阅条目是另一条文档的回复，需要机器可读父关系；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/entry.py)。
- **原版缺口**：link可人工加关系但没有Atom threading扩展或in_reply_to入口
- **交付及模块**：增加条目级讨论关系扩展，输出父引用、href、source与可选计数；`feedgen/entry.py:FeedEntry`, `feedgen/ext/base.py`。
- **兼容与实际依赖**：不联网获取父记录；默认XML保持；缺父ID不能仅靠显示标题猜关系；步骤依赖：无。
- **正常验收**：两条回复可声明同一父记录并保留可选链接/类型
- **异常／边界验收**：跨feed父项、多父项政策、自引用、非法计数和RSS导出兼容提示明确
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 07．Atom条目语言与基地址

- **来源／场景**：同一feed里每篇文档语言/相对资源基准不同；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：FeedGenerator.language可设feed xml:lang，FeedEntry没有language/xml:base接口
- **交付及模块**：一次增加条目/内容的语言与基地址元数据，并说明继承关系；`feedgen/feed.py:FeedGenerator.language`, `feedgen/entry.py:FeedEntry.atom_entry`。
- **兼容与实际依赖**：默认继承feed语言；不自动翻译内容、不读取外部资源；RSS按可用字段降级；步骤依赖：无。
- **正常验收**：中英两条entry分别带正确xml:lang，内容基地址明确保留
- **异常／边界验收**：无条目值时继承、空值清除继承、相对base、非法语言标签与内容多语言有边界
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 08．可复现的默认时间来源

- **来源／场景**：相同业务数据在两次离线构建应产生同样订阅文件；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：FeedGenerator/FeedEntry构造时各自datetime.now，调用方可手动updated/lastBuildDate但无统一clock
- **交付及模块**：增加显式clock/默认时间策略，让整次构建的缺省时间一致并可冻结；`feedgen/feed.py:FeedGenerator.__init__`, `feedgen/entry.py:FeedEntry.__init__`。
- **兼容与实际依赖**：显式日期始终优先；默认仍可用当前时间；不能默默按运行时改已发布的published；步骤依赖：无。
- **正常验收**：冻结clock构建两次的规范输出逐字节一致，entry默认与feed相同
- **异常／边界验收**：naive clock、跨时区、显式覆盖、复制builder和扩展时间字段有明确规则
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 09．按条目ID更新

- **来源／场景**：周期性导入同一文档ID需更新正文而非添加重复条目；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：add_entry仅插入，entry返回列表，remove按对象/索引；无upsert_entry索引合同
- **交付及模块**：新增按显式ID的查找/更新/插入，冲突与顺序规则可选择；`feedgen/feed.py:FeedGenerator.add_entry`, `feedgen/feed.py:FeedGenerator.entry`。
- **兼容与实际依赖**：原add_entry允许重复的行为可保留；新严格入口不把无ID条目猜为同一文档；步骤依赖：无。
- **正常验收**：同ID更新保持原位置，新增ID按选项append/prepend
- **异常／边界验收**：已有重复ID、空ID、ID变化与部分字段省略时保留/清空策略明确
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 10．可序列化订阅快照

- **来源／场景**：本地工具需保存builder状态后继续修改而不解析生成XML；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：builder用私有字段和扩展实例，无版本化snapshot往返合同
- **交付及模块**：增加显式to/from snapshot，保存格式中立字段、日期与声明的扩展状态；`feedgen/feed.py:FeedGenerator`, `feedgen/entry.py:FeedEntry`。
- **兼容与实际依赖**：不直接dump __dict__或反序列化任意类；扩展需声明可序列化能力；步骤依赖：无。
- **正常验收**：保存恢复后RSS/Atom业务字段一致，恢复对象可独立修改
- **异常／边界验收**：未知schema、未知扩展、naive时间、重复ID及snapshot缺字段有明确错误
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 11．受限条目窗口

- **来源／场景**：订阅首页只包含最新N篇，归档全量仍保留；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：entry列表可调用方排序切片，但没有window的日期/相等顺序/复制合同
- **交付及模块**：新增只读条目视图或导出窗口，支持明确日期键、排序和数量上限；`feedgen/feed.py:FeedGenerator.entry`, `feedgen/entry.py:FeedEntry.updated`。
- **兼容与实际依赖**：默认导出顺序保持；不改变原列表或把updated/published互相猜测替代；步骤依赖：无。
- **正常验收**：按published取最新3条，时间相同保持原先顺序
- **异常／边界验收**：缺日期、负数量、0、时区不同和窗口边界相等的记录有确定结果
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 12．多订阅合并

- **来源／场景**：把多个文档目录汇成一个feed且要保留来源；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：没有merge；手动entry追加无法统一feed元数据和ID冲突规则
- **交付及模块**：增加合并预览与显式应用，来源、重复ID和字段冲突均保留决策；`feedgen/feed.py:FeedGenerator.entry`, `feedgen/entry.py:FeedEntry.source`。
- **兼容与实际依赖**：不自动把不同ID相似标题合并；不覆盖原builder；与单库upsert不同，处理多库元数据；步骤依赖：无。
- **正常验收**：两个feed公共条目按所选冲突策略合并，独有条目及来源保持
- **异常／边界验收**：相同ID不同正文、日期冲突、扩展版本、无ID条目和输入顺序都可复核
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 13．原子文件写出

- **来源／场景**：本地归档文件已存在，写入失败不能留下截断XML；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：atom_file/rss_file调用ElementTree.write直接写目标，无原子选项
- **交付及模块**：新增原子输出，在同目录临时文件写完后替换目标并记录最终字节数；`feedgen/feed.py:FeedGenerator.atom_file`, `feedgen/feed.py:FeedGenerator.rss_file`。
- **兼容与实际依赖**：现有file-like流入口保持；不能对任意file-like宣称原子替换；步骤依赖：无。
- **正常验收**：Atom/RSS成功写入后可重读；完成前旧文件保持
- **异常／边界验收**：写满、编码失败、扩展异常、替换失败及取消只清本次临时文件并保留旧文件
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 14．流式XML导出

- **来源／场景**：较大的文档清单不希望同时建立整棵XML树和完整bytes；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：_create_atom/rss先建立全树，str/file再整体序列化；无iter_atom/rss
- **交付及模块**：增加有序增量输出，先验证必需元数据再逐条写entry，公开partial失败状态；`feedgen/feed.py:_create_atom`, `feedgen/feed.py:_create_rss`, `feedgen/entry.py:FeedEntry.atom_entry`。
- **兼容与实际依赖**：原字符串入口保持；扩展若依赖全树需明确不支持或回退；不能把部分输出叫完整feed；步骤依赖：无。
- **正常验收**：流输出拼接解析后与全树业务字段一致，额外内存不随总条目数线性增长
- **异常／边界验收**：中途条目无效、取消、命名空间、空feed和file-like短写有明确合同
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 15．每次导出选择扩展

- **来源／场景**：相同builder给两个客户端导出不同扩展集合；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：load/register可按atom/rss启用，导出extensions只有总布尔开关
- **交付及模块**：增加每次导出的namespace允许/排除集合，不修改builder注册状态；`feedgen/feed.py:FeedGenerator.register_extension`, `feedgen/feed.py:FeedGenerator.atom_str`。
- **兼容与实际依赖**：已有总开关兼容；默认全部已启用扩展；依赖扩展不能隐式缺失；步骤依赖：无。
- **正常验收**：同builder分别导出DC与podcast子集，普通字段相同且互不污染
- **异常／边界验收**：未知namespace、互相依赖扩展、entry级扩展和all=False优先关系明确
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 16．完整Atom来源元数据

- **来源／场景**：转发文档需保存原feed的id/updated/author等；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/entry.py)。
- **原版缺口**：FeedEntry.source文档明确只支持title和URL，Atom其余source子元素未支持
- **交付及模块**：扩展为受校验Atom source对象，保留id/title/updated/author/link等明确字段；`feedgen/entry.py:FeedEntry.source`, `feedgen/entry.py:FeedEntry.atom_entry`。
- **兼容与实际依赖**：原source(url,title)继续；RSS仍只投影其可表达的URL/title，损失可说明；步骤依赖：无。
- **正常验收**：转发条目输出完整原feed来源且不替换本entry作者/日期
- **异常／边界验收**：缺source id、多个作者/链接、语言继承、非法字段和RSS降级有明确结果
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 17．Podcast2.0扩展

- **来源／场景**：普通播客订阅需章节、转录稿和参与人员元数据；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/ext/podcast.py)。
- **原版缺口**：内建podcast是iTunes扩展，没有podcast20；generic registry是现有替代
- **交付及模块**：新增有边界的Podcast2.0扩展，先交付章节、转录稿与人员这套完整可用集合；`feedgen/ext/podcast.py`, `feedgen/ext/podcast_entry.py`, `feedgen/ext/base.py`。
- **兼容与实际依赖**：不把已有iTunes字段重复计数；不抓取转录稿或媒体；未覆盖标签明确不支持；步骤依赖：无。
- **正常验收**：单集可同时输出章节链接、带type的转录稿和有角色的人员
- **异常／边界验收**：多语言转录稿、重复人员、缺URL/type、空扩展和Atom投影政策有断言
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 18．正文生成纯文本摘要

- **来源／场景**：文档只有HTML正文，希望按明确规则生成可读摘要；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/entry.py)。
- **原版缺口**：summary/description接调用方文字，未提供summary_from_content
- **交付及模块**：增加可选本地摘要提取，去标签保留可见文字、按字素/词边界截断并保留人工摘要优先；`feedgen/entry.py:FeedEntry.content`, `feedgen/entry.py:FeedEntry.summary`。
- **兼容与实际依赖**：不做生成式概括或语义改写；默认不自动修改已有summary；引用型src内容不联网读取；步骤依赖：无。
- **正常验收**：简单HTML正文产生无标签摘要，中文/英文截断符合长度和省略号选项
- **异常／边界验收**：实体、代码块、多段落、空内容、非文本内容和人工摘要均不被错误覆盖
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 19．订阅资源地址重写

- **来源／场景**：离线生成后目标站点基地址变化，所有资源需按同一规则改写；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/feed.py)。
- **原版缺口**：link/content src/enclosure/source由各setter保存，没有统一rewrite_uris访问器
- **交付及模块**：新增显式纯函数URI改写，遍历已知字段并由扩展声明其资源位置；`feedgen/feed.py:FeedGenerator.link`, `feedgen/entry.py:FeedEntry.link`, `feedgen/entry.py:FeedEntry.enclosure`。
- **兼容与实际依赖**：默认不改地址；不把entry id当URL盲改，正文HTML内链接需显式选择额外解析；步骤依赖：无。
- **正常验收**：原站点前缀迁移后feed/entry/enclosure链接一致，文档ID保持
- **异常／边界验收**：相对地址、片段、不同scheme、回调异常和未知扩展字段有可预览修改清单
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。

## 20．由本地清单生成真实订阅的CLI

- **来源／场景**：现有python -m feedgen只生成写死的演示feed；[固定源码](https://github.com/lkiesow/python-feedgen/blob/97260abb1793eb164c458c10b493690beb413f6d/feedgen/__main__.py)。
- **原版缺口**：__main__.py有演示命令但不读用户manifest；并非没有任何CLI
- **交付及模块**：新增本地JSON清单输入，验证字段映射后可选RSS/Atom与输出路径，保留演示兼容入口；`feedgen/__main__.py:main`, `feedgen/feed.py:FeedGenerator`。
- **兼容与实际依赖**：只读显式本地清单，不访问订阅网络；声明日期和编码要求；未支持扩展不任意加载代码；步骤依赖：无。
- **正常验收**：两条用户文档从清单生成真实RSS/Atom文件并可重读标题/ID
- **异常／边界验收**：非法JSON、未知字段、缺必填、重复ID、输出不可写和部分生成失败给准确非零状态
- **原生回归**：`tests/test_feed.py`, `tests/test_entry.py`, `tests/test_main.py`, `tests/test_extensions/test_podcast.py`, `tests/test_extensions/test_dc.py`, `tests/test_extensions/test_media.py`。
