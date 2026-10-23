# feedparser：二十步真实工程迭代路线

固定 [kurtmckee/feedparser@a22c5521cbb109871f1a2318948581901bd47e26](https://github.com/kurtmckee/feedparser/tree/a22c5521cbb109871f1a2318948581901bd47e26)，原生证据见 [单仓审查](./feedparser.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．JSON条目修改日期

- **来源／场景**：JSON Feed使用date_modified表示修订时刻；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/parsers/json.py)。
- **原版缺口**：JSONParser先检查date_updated却读取date_modified；实测合法date_modified被忽略
- **交付及模块**：修正字段判断与取值一致性，保留原日期及UTC解析结果；`feedparser/parsers/json.py:JSONParser.parse_entry`。
- **兼容与实际依赖**：不把published当修改时间；旧错误拼写若保留必须显式兼容且正确字段优先；步骤依赖：无。
- **正常验收**：只有date_modified时updated/updated_parsed出现且时间正确
- **异常／边界验收**：同时有新旧拼写、无日期、非法日期、带偏移和小数秒按日期合同处理
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 02．JSON与XML结果结构一致

- **来源／场景**：通用订阅客户端用content/tags/enclosures访问器处理两种格式；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/parsers/json.py)。
- **原版缺口**：JSON content是单dict且text/html二选一，分类写category，附件直接写enclosures；实测tags/enclosures访问器取不到已输入值
- **交付及模块**：统一JSON适配到既有content列表、tags结构和rel=enclosure links，保留双正文；`feedparser/parsers/json.py:JSONParser.parse_entry`, `feedparser/util.py:FeedParserDict`。
- **兼容与实际依赖**：这是一次通用结果合同修复，不按三种字段拆步骤；兼容旧原始字段访问需明确迁移；步骤依赖：无。
- **正常验收**：同义JSON/RSS/Atom解析后通用正文/分类/附件消费者都能工作
- **异常／边界验收**：同时HTML和text、空tags、多附件、附件缺字段及原始dict检查不会出现两个矛盾来源
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 03．已声明JSON1.1的元数据补全

- **来源／场景**：1.1使用authors数组和语言覆盖；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/parsers/json.py)。
- **原版缺口**：版本表接受1.1，但只读单author，未映射authors/language；实跑这些值消失
- **交付及模块**：补全已声明版本的多作者、头像与feed/item语言继承等明确元数据；`feedparser/parsers/json.py:JSONParser.feed`, `feedparser/parsers/json.py:JSONParser.parse_author`。
- **兼容与实际依赖**：标明是对现有1.1适配的补完，不是新宣称支持该版本；legacy author兼容规则明确；步骤依赖：无。
- **正常验收**：feed两作者/item一作者及语言覆盖按数组顺序保留，缺item作者可按规则继承
- **异常／边界验收**：空数组与缺数组不同、author与authors同时出现、未知语言和错误成员类型不静默吞值
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 04．JSON自定义字段保留

- **来源／场景**：文档订阅用_archive/_review记录本地扩展；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/parsers/json.py)。
- **原版缺口**：JSONParser只拷贝固定字段，自定义下划线字段丢弃；无保留选项
- **交付及模块**：增加opt-in未知扩展字段保留区，区分原生字段与原始JSON；`feedparser/parsers/json.py:JSONParser.FEED_FIELDS`, `feedparser/parsers/json.py:JSONParser.ITEM_FIELDS`。
- **兼容与实际依赖**：默认结果不强行膨胀；不把自定义字段提升为内建语义；深层对象只作为数据；步骤依赖：无。
- **正常验收**：feed/item扩展对象完整保留，可序列化后对照输入
- **异常／边界验收**：名称与内建字段冲突、嵌套列表、大字段预算及无下划线未知字段策略明确
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 05．订阅字段统一校验

- **来源／场景**：本地批量导入遇到items类型错或条目缺必需ID；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/parsers/json.py)。
- **原版缺口**：容错bozo与XML解析错误不是完整结构验证；没有validate_feed报告
- **交付及模块**：新增显式格式/版本校验，汇总字段路径、严重程度及已提取数据可用范围；`feedparser/parsers/json.py:JSONParser.feed`, `feedparser/api.py:parse`。
- **兼容与实际依赖**：不让默认容错解析突然严格拒绝旧RSS；校验与检测到具体格式分开；步骤依赖：无。
- **正常验收**：多个JSON条目缺ID/正文时一次报告各自路径，合法RSS按对应规则检查
- **异常／边界验收**：空feed、items非数组、数组内标量、未知版本和扩展字段不能混成同一错误
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 06．日期的偏移与精度详情

- **来源／场景**：档案需要保留小数秒与原始时区偏移而不只UTCstruct_time；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/datetimes/__init__.py)。
- **原版缺口**：published_parsed/updated_parsed统一为struct_time，原字符串虽保留但无日期详情对象
- **交付及模块**：新增parse_date_detail/日期旁路元数据，记录原精度、偏移、推断与规范化结果；`feedparser/datetimes/__init__.py`, `feedparser/parsers/json.py:JSONParser.parse_entry`。
- **兼容与实际依赖**：现有parsed tuple保持；无时区的旧RSS不能被伪称准确UTC；不丢原字符串；步骤依赖：无。
- **正常验收**：带.123及+08:00的日期详情可还原精度和偏移，UTC表示一致
- **异常／边界验收**：闰秒、无年份、时区缩写、非法日期及不支持精度明确标记而非猜值
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 07．单次解析日期处理器

- **来源／场景**：两个导入任务需要不同的私有旧日期格式；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/datetimes/__init__.py)。
- **原版缺口**：registerDateHandler修改全局handler列表，没有调用级Registry
- **交付及模块**：增加显式DateHandlerRegistry和parse参数，使自定义处理器只作用于本次解析；`feedparser/datetimes/__init__.py:registerDateHandler`, `feedparser/api.py:parse`。
- **兼容与实际依赖**：现有全局注册兼容默认；内建顺序不变；自定义处理器失败不阻断后续合法处理器；步骤依赖：无。
- **正常验收**：两个registry交错解析只识别各自自定义日期格式
- **异常／边界验收**：异常返回、错误tuple长度、重复处理器、并发与嵌套解析不污染其他调用
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 08．跨格式人物字段视图

- **来源／场景**：客户端需统一遍历作者和贡献者，不手写多级fallback；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/util.py)。
- **原版缺口**：FeedParserDict含author/author_detail等历史映射，JSON/RSS/Atom人数形态不同，缺normalize_people
- **交付及模块**：提供只读人物视图，保留角色、姓名、邮箱、URI及原字段来源；`feedparser/util.py:FeedParserDict`, `feedparser/namespaces/_base.py`。
- **兼容与实际依赖**：不把显示字符串凭空拆成可靠邮箱/姓名；保留原结果与角色区别；步骤依赖：无。
- **正常验收**：Atom多作者、RSS单作者和JSON authors均得到有序人物记录
- **异常／边界验收**：组织名、缺姓名、重复角色、只有邮箱及feed继承人与entry显式人不混淆
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 09．无ID条目的明确身份策略

- **来源／场景**：旧RSS条目缺guid，客户端需稳定对账；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/util.py)。
- **原版缺口**：parse不生成通用entry_identity，调用方自行拼title/link/date
- **交付及模块**：增加显式身份助手，优先规范ID，其次由选定字段生成稳定摘要并记录可靠性；`feedparser/util.py:FeedParserDict`, `feedparser/api.py:parse`。
- **兼容与实际依赖**：默认不写假ID进原结果；不以相似标题自动判相同内容；步骤依赖：无。
- **正常验收**：有guid/Atom id保持；缺ID的同一条目按固定策略重复计算一致
- **异常／边界验收**：同标题不同link、跟踪参数、缺日期、Unicode归一化和字段缺失各有明确边界
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 10．订阅结果增量合并

- **来源／场景**：本地保存上次feed，本轮需区分新条目和修订；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/api.py)。
- **原版缺口**：只返回当次entries，无merge_feeds的冲突/修订合同
- **交付及模块**：增加纯数据合并与变更清单，按显式身份策略识别新增、修订与未变化；`feedparser/api.py:parse`, `feedparser/util.py:FeedParserDict`。
- **兼容与实际依赖**：不将本轮没出现条目自动删除；不依赖网络抓取；原输入不被修改；步骤依赖：无。
- **正常验收**：新旧两组结果可得到正确新增与同ID正文修订，保留来源
- **异常／边界验收**：同ID冲突、无ID、时刻倒退、字段省略及重复项有确定策略
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 11．分页与归档关系视图

- **来源／场景**：本地已下载多页feed，需要知道next/previous/archive关系；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/parsers/json.py)。
- **原版缺口**：通用links可含关系，但不同格式需要客户端自行查找，无pagination_info
- **交付及模块**：新增只读分页关系提取，统一Atom links与JSON next_url等映射并保留来源；`feedparser/parsers/json.py:JSONParser.FEED_FIELDS`, `feedparser/namespaces/_base.py`。
- **兼容与实际依赖**：只解释已解析关系，不自动获取下一页；未知关系保留原值；步骤依赖：无。
- **正常验收**：Atom下一页和JSON next_url得到一致关系视图，多个候选保留
- **异常／边界验收**：相对地址、重复rel、循环链接、缺base与未知archive属性有明确提示
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 12．增量产出条目

- **来源／场景**：较大本地订阅希望逐条交给下游；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/api.py)。
- **原版缺口**：parse积累entries后返回，严格XML失败后可重试loose；无iter_entries公开合同
- **交付及模块**：提供增量解析模式，说明strict/loose重试与何时可以发布条目；`feedparser/api.py:_parse_file_inplace`, `feedparser/parsers/strict.py`, `feedparser/parsers/loose.py`。
- **兼容与实际依赖**：不能在loose回退时重复发布已发条目；默认完整结果保持；步骤依赖：无。
- **正常验收**：有效RSS逐条产出与parse最终条目一致，顺序和元数据保留
- **异常／边界验收**：中途截断、恢复、取消、超长单条与feed尾部元数据明确表示partial状态
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 13．解析工作预算

- **来源／场景**：本地交互式导入需要输入/条目/耗时预算及取消；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/api.py)。
- **原版缺口**：optimistic_encoding_detection只控制编码前缀探测，不是ParseBudget
- **交付及模块**：增加显式字节、条目、文本字段和取消预算，保留停止原因与已解析范围；`feedparser/api.py:parse`, `feedparser/mixin.py:XMLParserMixin`。
- **兼容与实际依赖**：预算结束不能自报完整解析成功；默认无预算行为保持；步骤依赖：无。
- **正常验收**：预算足够时与原结果一致，达到条目上限后有准确未完成状态
- **异常／边界验收**：零/负预算、超大单条、编码转换阶段取消、JSON与XML一致，不错误关闭调用方流
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 14．明确文本与文件入口

- **来源／场景**：一段普通订阅文字不应因恰像路径而选择另一输入分支；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/api.py)。
- **原版缺口**：parse统一URL/路径/文本，文档建议用StringIO/BytesIO消除歧义；无parse_text/parse_bytes
- **交付及模块**：增加明确纯文本、字节和本地文件的薄入口，并约定编码及base参数；`feedparser/api.py:_open_resource`, `feedparser/api.py:parse`。
- **兼容与实际依赖**：保留现有parse；新文本入口只解释提供的文字，不隐式另读路径；流归属清晰；步骤依赖：无。
- **正常验收**：同一feed通过显式文本/字节/文件入口得到相同内容
- **异常／边界验收**：空文字、像路径的普通字符串、BOM、未知编码和不可seek流得到确定结果
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 15．归一化字段来源追踪

- **来源／场景**：导入者要知道summary来自description还是content；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/mixin.py)。
- **原版缺口**：结果包含统一字段，但没有原格式字段/输入位置到输出字段的provenance合同
- **交付及模块**：新增可选来源表，记录字段路径、原标签/JSON键、转换及可得位置；`feedparser/mixin.py:XMLParserMixin`, `feedparser/parsers/json.py:JSONParser.parse_entry`。
- **兼容与实际依赖**：原字段结果保持；重写、推断与直接复制分别标明；无坐标时不猜；步骤依赖：无。
- **正常验收**：RSS description与JSON summary分别关联正确统一字段来源
- **异常／边界验收**：别名覆盖、多条同名元素、继承xml:lang、编码重解码与合并正文均可追踪
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 16．保留多条恢复诊断

- **来源／场景**：一个旧RSS同时有编码覆盖和日期问题，需完整查看；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/api.py)。
- **原版缺口**：bozo/bozo_exception以单一异常为主要入口，缺少稳定的多诊断返回合同
- **交付及模块**：增加诊断列表，区分阶段、严重程度、原错误及可用结果范围；`feedparser/api.py:parse`, `feedparser/encodings.py:convert_file_to_utf8`。
- **兼容与实际依赖**：原bozo兼容；警告不自动升级成不可用；不能只保存最后一个异常；步骤依赖：无。
- **正常验收**：多阶段问题各保留一条有序诊断，正常feed列表为空
- **异常／边界验收**：严格失败后loose成功、重复相同警告、未知位置和异常对象不可JSON序列化均有稳定表示
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 17．稳定结果快照

- **来源／场景**：本地缓存解析结果需跨进程可比较和重读；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/util.py)。
- **原版缺口**：直接dict/json遇异常对象与历史别名有歧义，没有canonical JSON版本合同
- **交付及模块**：新增规范快照读写，明确真实键、日期tuple、异常摘要及schema版本；`feedparser/util.py:FeedParserDict`, `feedparser/api.py:parse`。
- **兼容与实际依赖**：不序列化任意Python对象；不把get的兼容fallback写成真实字段；保留原始日期文本；步骤依赖：无。
- **正常验收**：正常RSS/Atom/JSON结果往返保持业务字段与时间信息
- **异常／边界验收**：bozo异常、bytes字段、同名别名、未知schema及空结果不会悄悄丢失
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 18．统一可读正文选择

- **来源／场景**：本地阅读器优先纯文本，没有时才从HTML提取文字；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/util.py)。
- **原版缺口**：content/summary/detail由调用方组合，缺entry_text的偏好和来源合同
- **交付及模块**：增加只读正文助手，明确类型优先级、语言偏好和HTML到文字的有限转换；`feedparser/util.py:FeedParserDict`, `feedparser/parsers/json.py:JSONParser.parse_entry`。
- **兼容与实际依赖**：不生成摘要或改原正文；不获取content src；保留选中来源/原类型；步骤依赖：无。
- **正常验收**：同时text/html时按偏好选对，缺正文回退summary并说明
- **异常／边界验收**：多语言、空正文、外部src、未知MIME与只有标题的情况不伪造正文
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 19．本地文件解析CLI

- **来源／场景**：档案维护者希望终端将已有feed文件转为结构化结果；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/__init__.py)。
- **原版缺口**：包公开parse等API，未提供稳定的用户文件→规范结果CLI
- **交付及模块**：增加本地文件/stdin入口、格式概要/JSON选项与明确退出码；`feedparser/__init__.py`, `feedparser/api.py:parse`。
- **兼容与实际依赖**：默认不抓取订阅URL；沿用API原结果，不自报验证成功；用户显式选择strict/容错输出；步骤依赖：无。
- **正常验收**：有效RSS/Atom文件可输出标题、条目及日期，JSON结果可解析
- **异常／边界验收**：无输入、文件不可读、bozo但可恢复、无条目与未知格式的状态准确区分
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。

## 20．命名空间扩展的调用级注册

- **来源／场景**：组织自定义的文档分类namespace需可复用处理器；[固定源码](https://github.com/kurtmckee/feedparser/blob/a22c5521cbb109871f1a2318948581901bd47e26/feedparser/namespaces/__init__.py)。
- **原版缺口**：namespaces以实现模块组合，用户可维护fork/猴子补丁；无register_namespace_handler合同
- **交付及模块**：提供显式registry映射namespace URI与本地处理器，声明输出字段与冲突策略；`feedparser/namespaces/__init__.py`, `feedparser/mixin.py:XMLParserMixin`。
- **兼容与实际依赖**：不改变内建namespace默认；不从输入加载代码；解析实例间隔离；步骤依赖：无。
- **正常验收**：注册自定义文档分类后得到约定字段，不注册时保留普通未知元素处理
- **异常／边界验收**：前缀变更同URI、字段冲突、处理器异常、嵌套作用域和并发registry不互相污染
- **原生回归**：`tests/test_json.py`, `tests/test_feedparser_dict.py`, `tests/test_date_parsers.py`, `tests/test_encoding.py`, `tests/test_ill_formed.py`, `tests/test_parse_parameters.py`, `tests/test_well_formed.py`。
