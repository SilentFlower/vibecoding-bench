# Natsort 二十步迭代研究路线

固定[SethMMorton/natsort@e9a3a2a307580a1f2be8c57bba50fba45789ada0](https://github.com/SethMMorton/natsort/tree/e9a3a2a307580a1f2be8c57bba50fba45789ada0)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已存在INT/FLOAT/SIGNED/NOEXP/NUMAFTER/PATH、Unicode数字、NFD/NFKD、locale、大小写组合、NANLAST、PRESORT、nested key、索引排序、os_sorted、PureWindowsPath对象及CLI-z输入；不重复计为新增。

## 01．CLI整数筛选保留完整整数精度

- **类型／来源与场景**：bug_fix；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/__main__.py)；离线编号列表排除9007199254740992时不能同时误删相邻编号。
- **原版现状／替代**：默认int排序，但--exclude参数和匹配数字都转float；实跑两个相邻16位编号全被排除。
- **交付与模块**：按number-type选择精确int/float筛选转换，筛选阈值参数不提前强转float；范围/反选同样修复。；`natsort/__main__.py`。
- **兼容边界**：float/real既有阈值语义保持；int阈值含小数时需明确支持精确比较或拒绝，不截断。
- **正常验收**：排除前一个编号后保留item9007199254740993，sort/filter对同数字解释一致。
- **异常／边界验收**：负数、指数选项、Unicode数字、范围边界、非数字条目和多筛选组合。
- **原生回归**：`tests/test_main.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 02．可选精确十进制数值排序策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/utils.py)；科学记录含1e399/1e400和精细小数，不希望有限float把不同值都折为inf。
- **原版现状／替代**：ns.REAL明确使用float，实跑1e400/1e399同键保持输入序；无DECIMAL选项。
- **交付与模块**：增加显式Decimal或归一化十进制系数/指数比较后端，保持有限数精度并定义inf/NaN。；`natsort/utils.py`、`natsort/natsort.py`、`natsort/ns_enum.py`。
- **兼容边界**：不把文档已声明float语义直接改为高成本Decimal；默认键输出保持。
- **正常验收**：精确模式把1e399排在1e400前，相邻精细小数分得开。
- **异常／边界验收**：正负极大/极小指数、负零、真inf/NaN、Unicode数值和两后端一致声明范围。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`、`tests/test_string_component_transform_factory.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 03．数字识别范围可以选择ASCII或Unicode类别

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/utils.py)；产品版本编号只把0-9当数字，而教学数字列表仍识别各文字数字。
- **原版现状／替代**：默认Unicode regex包含decimal/digit/numeric，用户只能预转换；没有ASCII_ONLY/类别策略。
- **交付与模块**：增加明确digit_scope参数或策略对象，预编译相应tokenizer并保留现有默认。；`natsort/utils.py`、`natsort/ns_enum.py`、`natsort/natsort.py`。
- **兼容边界**：已有Unicode数字支持保持；不把单个Unicode罗马数字支持冒充新能力。
- **正常验收**：ASCII模式不把a٣解析为数字3，Unicode模式仍按数值排序。
- **异常／边界验收**：全角、上标、分数、混合数字串、NFKD归一化与FLOAT/INT组合。
- **原生回归**：`tests/test_regex.py`、`tests/test_unicode_numbers.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 04．符号可按上下文解释而非一律相邻负号

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/utils.py)；item-2是编号分隔符，而温度-2是负数，业务需要显式区分。
- **原版现状／替代**：SIGNED一律吸收紧邻+/-；实跑item-10排item-2前，当前符合开关语义。
- **交付与模块**：新增contextual sign策略，允许声明前缀/分隔上下文或token回调决定符号。；`natsort/utils.py`、`natsort/ns_enum.py`、`natsort/natsort.py`。
- **兼容边界**：默认SIGNED/UNSIGNED保持；不全局猜测日期/编号语义；指数内部符号仍属于指数。
- **正常验收**：同一策略下item-2/item-10按编号2/10，温度按真正负数顺序。
- **异常／边界验收**：串首、双符号、指数、Unicode减号、用户回调异常和重复token。
- **原生回归**：`tests/test_regex.py`、`tests/test_natsorted.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 05．提供声明版本规范的排序适配器

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；版本列表包含1.0rc1/1.0/1.0.post1，不能把自然数字顺序当发布顺序。
- **原版现状／替代**：没有version_sorted；普通natsorted只识别数字/文本，调用方可用packaging.Version作key。
- **交付与模块**：新增可选PEP440/明确SemVer适配入口，接收非法版本策略和稳定回退。；`natsort/natsort.py`。
- **兼容边界**：不同规范不混为一谈；不改变普通自然排序；可选packaging版本与许可需冻结。
- **正常验收**：所选规范的pre/final/post或SemVer prerelease符合官方规则。
- **异常／边界验收**：非法版本、epoch/local/build、相等规范化版本、混合None及无可选依赖时错误。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 06．可按显式单位注册表排序数量文本

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；本地规格2 m/150 cm/900 mm应按同一长度维度比较。
- **原版现状／替代**：数字与单位作为独立文本，没有quantity_sorted；可调用方先换算。
- **交付与模块**：增加可选quantity key适配，单位表带精确比例/偏移和维度，使用声明的数值后端。；`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：默认不识别任意单位；未知或维度不同明确策略，不把MB/MiB自动当相同。
- **正常验收**：长度表归一后900mm<150cm<2m，原始文本原样返回。
- **异常／边界验收**：温度偏移、负数、空白、locale小数、维度冲突、未知单位和精度。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 07．提供按已声明格式解析日期字段的排序适配

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；日志日期是DD/MM/YYYY，逐数字比较不能得到时间先后。
- **原版现状／替代**：无datetime_sorted；可外部datetime.strptime作为key。
- **交付与模块**：新增date key adapter，必须提供格式/时区/缺失策略，解析一次并返回可解释错误位置。；`natsort/natsort.py`。
- **兼容边界**：不默认自动猜歧义日期；普通数字文本排序保持；naive/aware不能静默混排。
- **正常验收**：31/12/2025在01/01/2026前，原记录保留。
- **异常／边界验收**：非法日历日、多格式命中歧义、DST、无时区、空值和缓存失效。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 08．多字符罗马数字采用显式文本规则

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/utils.py)；书卷Chapter IX与Chapter V需要按9和5，而非字母顺序。
- **原版现状／替代**：Unicode单字符Ⅳ已按FLOAT支持；ASCII多字符IV/IX无ROMAN策略。
- **交付与模块**：新增opt-in Roman tokenizer，限定词界、标准写法与大小写规则。；`natsort/utils.py`、`natsort/ns_enum.py`、`natsort/natsort.py`。
- **兼容边界**：不把普通单词mix中的mix任意解释109；默认行为不变。
- **正常验收**：独立Chapter V/IX/X按5/9/10，Unicode字符原能力继续。
- **异常／边界验收**：非法IIII/IL、大小写、词中片段、零/负罗马数与阿拉伯数字混排。
- **原生回归**：`tests/test_regex.py`、`tests/test_natsorted.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 09．缺失值和异类值可以声明独立排序优先级

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/utils.py)；表格希望None最后、NaN次后、真实+inf仍与数字比较。
- **原版现状／替代**：NANLAST已存在，内部把None/NaN放在inf附近，并有固定尾标记；无调用级独立missing策略。
- **交付与模块**：新增显式null/NaN/type precedence策略，以类型标签构建总序键，避免应用自写不兼容tuple。；`natsort/utils.py`、`natsort/natsort.py`。
- **兼容边界**：保留NANLAST当前行为；不重复算作新增；外部自定义可比较对象的接纳范围明确。
- **正常验收**：有限数、真实inf、NaN、None各组顺序按声明，reverse语义清楚。
- **异常／边界验收**：Decimal NaN、嵌套值、bytes/str、空文本、未知类型和原key兼容。
- **原生回归**：`tests/test_parse_number_function.py`、`tests/test_natsorted.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 10．多列排序可逐列指定算法和方向

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；商品先按category自然升序，再按batch数字降序，空价格放末尾。
- **原版现状／替代**：key可返回嵌套tuple/list且会递归处理，但只有全局alg/reverse，没有逐列策略。
- **交付与模块**：新增FieldSortSpec与multisorted/keygen，逐列key/alg/reverse/missing独立。；`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：普通嵌套key支持保持；不把已有tuple排序说成完全不支持多字段。
- **正常验收**：两列混合方向及各自INT/REAL结果与稳定多轮参考排序一致。
- **异常／边界验收**：列缺失、变长记录、相等列稳定性、getter异常和嵌套tuple。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 11．locale排序上下文可以独立于进程全局

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/compat/locale.py)；本地应用同时展示两种语言列表，不能互相更改locale。
- **原版现状／替代**：natsort_keygen无locale参数，compat后端从当前进程locale创建转换器。
- **交付与模块**：新增显式LocaleContext，优先用每实例ICU Collator和冻结数值分隔信息；不支持时明确拒绝。；`natsort/compat/locale.py`、`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：现有全局locale默认保持；标准库setlocale不能被包装成假线程局部。
- **正常验收**：两个context并行生成键互不串，创建后全局locale改变不影响已有配置。
- **异常／边界验收**：ICU缺失、语言回退、分隔符归一化、context序列化限制和backend版本。
- **原生回归**：`tests/test_compat_locale.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 12．排序键解释包含原文token与字符位置

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；界面解释为什么chapter02排在chapter10前。
- **原版现状／替代**：可以直接查看natsort_keygen产生的tuple，但原始span、归一化步骤和数值类型不再保留。
- **交付与模块**：新增explain_key返回阶段配置、原始token/span、归一化文本及最终比较键。；`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：普通key快速路径不额外保存轨迹；Unicode归一化前后索引分开，不伪报位置。
- **正常验收**：chapter02显示02转int2的准确原位置，最终键与正常key一致。
- **异常／边界验收**：NFKD长度变化、locale字节键、路径层级、bytes、嵌套记录及自定义key。
- **原生回归**：`tests/test_natsort_keygen.py`、`tests/test_utils.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 13．可选有界缓存重复值的自然排序键

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；同一批标签被多次重排，key解析结果可以重用。
- **原版现状／替代**：natsort_keygen复用工厂但不缓存每个输入键，无cached_keygen。
- **交付与模块**：提供显式有界LRU缓存，配置指纹包含alg/locale/backend，暴露清空与统计。；`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：默认不缓存；不可hash输入不强行repr作缓存键；用户key可变时需禁用或提供版本。
- **正常验收**：相同输入命中缓存且输出一致，容量淘汰和清空可验证。
- **异常／边界验收**：locale改变、不同策略、unhashable、内存上限、并发与异常结果不缓存。
- **原生回归**：`tests/test_natsort_keygen.py`、`tests/test_natsorted.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 14．大文件可在固定内存内完成自然排序

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；离线文本列表大于内存时，需要本地临时分块排序。
- **原版现状／替代**：natsorted最终调用sorted，会完整物化；没有external_sorted。
- **交付与模块**：新增external sorting API/CLI，分块生成键与稳定序号、临时落盘后归并，支持清理。；`natsort/natsort.py`、`natsort/__main__.py`。
- **兼容边界**：只用调用者指定本地临时目录；数据codec显式；不声称任意Python对象都可安全序列化。
- **正常验收**：小内存预算下结果与全量natsorted完全一致且相等键稳定。
- **异常／边界验收**：中断/磁盘满、超长单条、空文件、临时清理、不同encoding和键配置指纹。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_main.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 15．前K自然排序不必物化完整结果

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；仪表盘只显示最前100个标签，但输入是大迭代器。
- **原版现状／替代**：无nsmallest/nlargest，可自己heapq.nsmallest配keygen。
- **交付与模块**：新增自然排序topK接口，复用相同键策略并定义相等键稳定性、反向和索引返回。；`natsort/natsort.py`。
- **兼容边界**：不改变natsorted返回全列表；内存O(K)只针对选择存储，不虚称输入可少读。
- **正常验收**：K结果等于完整排序前K，相同键按输入先后。
- **异常／边界验收**：K0/负、K超过输入、生成器、NUMAFTER/NANLAST、索引选择和key异常。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 16．按相同自然策略归并多个已排序流

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；合并多份本地已排好序的章节清单。
- **原版现状／替代**：无merge_sorted；可heapq.merge(key=keygen)但策略匹配和乱序检查由用户承担。
- **交付与模块**：提供惰性merge_sorted，绑定policy并可校验每个输入非降序，稳定标记流与本地序号。；`natsort/natsort.py`。
- **兼容边界**：不偷偷重新全量排序乱序流；与外部排序相关但独立服务已有流输入。
- **正常验收**：三个流归并等于全量排序，next只消费必要前缀。
- **异常／边界验收**：空流、同键跨流稳定、reverse、配置不一致、输入中途异常和close。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 17．提供自然序列的范围查找与排名查询

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/natsort.py)；已排序的标签数组需要找chapter2到chapter10之间的条目。
- **原版现状／替代**：没有自然bisect/range接口；可标准库bisect配key但查找值也需转换。
- **交付与模块**：增加NaturalSortedIndex或bisect/range helpers，复用预计算键和原始索引，支持相等键左右界。；`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：不假定普通字典序数组已按自然序；不暗中重排原输入；更新失效规则明确。
- **正常验收**：chapter2/chapter02同键左右界正确，范围包含chapter3等且返回原项。
- **异常／边界验收**：空输入、重复键、reverse、policy改变、过期索引和查询值类型。
- **原生回归**：`tests/test_natsorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 18．CLI支持保留完整记录的CSV和JSONL排序

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/__main__.py)；本地CSV按章节列排序，但其他列、引号和换行必须保留。
- **原版现状／替代**：现CLI只排序整条文本，不解析列/JSON字段；单纯空格split会破坏数据。
- **交付与模块**：新增显式input-format与field spec，使用标准库csv/json解析，保留全部字段并选择输出格式。；`natsort/__main__.py`、`natsort/natsort.py`。
- **兼容边界**：默认逐行文本保持；只读本地stdin/文件，不增加远程数据访问；字段排序复用同一算法。
- **正常验收**：含逗号/引号的CSV和JSONL记录排序后字段值完整，逐列方向可配置。
- **异常／边界验收**：缺字段、非法JSON/CSV、空记录、嵌套字段、encoding/BOM与错误行号。
- **原生回归**：`tests/test_main.py`、`tests/test_natsorted.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 19．路径分隔与扩展名策略可显式声明

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/utils.py)；Linux上处理离线Windows路径清单，且业务长扩展名也需独立排序。
- **原版现状／替代**：PureWindowsPath对象已支持；普通str按宿主PurePath解释；suffix默认最多两段且每段长度<=5。
- **交付与模块**：新增PathSortPolicy指定flavor、root/drive排序、extension规则和已知复合后缀。；`natsort/utils.py`、`natsort/natsort.py`。
- **兼容边界**：默认PATH现有启发式保持；不把既有PureWindowsPath支持称缺失；只排序路径字符串，不访问文件系统。
- **正常验收**：同一Windows字符串在不同宿主同策略生成相同key，长扩展名按声明分离。
- **异常／边界验收**：UNC/drive-relative、隐藏文件、多点数字、重复后缀、尾分隔和POSIX反斜杠文字。
- **原生回归**：`tests/test_utils.py`、`tests/test_os_sorted.py`、`tests/test_natsort_keygen.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

## 20．CLI记录分隔和解码策略支持完整往返

- **类型／来源与场景**：enhancement；[来源](https://github.com/SethMMorton/natsort/blob/e9a3a2a307580a1f2be8c57bba50fba45789ada0/natsort/__main__.py)；文件名列表以NUL分隔，排序后还要交给同格式本地工具。
- **原版现状／替代**：已有-z只描述stdin按NUL分隔，输出仍print逐条换行；decoder只指定encoding，无errors策略。
- **交付与模块**：增加明确输入/输出分隔与encoding/errors配置，NUL记录输出不把记录内换行拆开。；`natsort/__main__.py`、`natsort/natsort.py`、`natsort/utils.py`。
- **兼容边界**：默认换行输出保持或提供标准兼容别名；不改变现有as_ascii/as_utf8严格解码默认。
- **正常验收**：包含换行字符的NUL记录排序后按NUL输出可无损恢复，UTF8边界正确。
- **异常／边界验收**：空输入/空记录保留规则、末尾分隔、无效编码、bytes原样选项和BrokenPipe清理。
- **原生回归**：`tests/test_main.py`、`tests/test_parse_bytes_function.py`。
- **实际依赖／步骤依赖**：默认运行仅Python标准库；本次使用内置fake_fastnumbers和系统locale后端，未安装fastnumbers/PyICU extras。测试pytest/pytest-cov/pytest-mock/Hypothesis/coverage，精确freeze已保存。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
