# PETL：二十步真实工程迭代路线

固定 [petl-developers/petl@cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b](https://github.com/petl-developers/petl/tree/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b)，详见[单仓审查](./petl.md)。共 20 步：18 项增强提案、2 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．XML 导出正确转义数据和属性（问题修复）

- 来源／场景：https://github.com/petl-developers/petl/issues/755
- 原版现状：toxml 用字符串模板插入原始数据；A&B 导出后 ElementTree 无法解析，已复现。
- 交付目标：内置 tag/name/attribute 样式分别正确转义文本与属性，保留字段数据。
- 影响模块：io/xml.py:toxml/_build_cols；io/text.py
- 兼容边界：自定义原始 XML 模板作为显式高级模式处理，不无条件二次转义已明确的 raw 片段。
- 正常验收：A&B、<tag>、单双引号导出并由独立 XML 解析器读回原值。
- 异常／边界：非法 XML 字符／元素名在写前拒绝或明确策略，Unicode、None、prologue 回归。
- 原生回归：petl/test/io/test_xml.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．拼接重复表头时不重复第一列值（问题修复）

- 来源／场景：https://github.com/petl-developers/petl/issues/561
- 原版现状：cat 单表 [x,x]/[1,2] 输出 [1,1]，hdr.index 总取第一个同名列，当前提交复现。
- 交付目标：显式按字段名及出现次序配对重复列；不能映射时提供清楚拒绝策略。
- 影响模块：transform/basics.py:CatView/itercat
- 兼容边界：普通唯一表头对齐与 missing 保持；默认不能静默丢第二个值。
- 正常验收：同一表重复字段两值保留，两输入的第n个同名字段按第n次匹配。
- 异常／边界：不等重复次数、指定输出 header、短行、空源与三个表拼接。
- 原生回归：petl/test/transform/test_basics.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．转换失败的独立问题表（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/81
- 原版现状：convert 可 failonerror/inline/errorvalue，但没有携带来源行号和字段的独立结构化错误输出。
- 交付目标：提供 convert_report，同时交付转换后的表及问题表，记录行、字段、异常类型。
- 影响模块：transform/conversions.py；transform/validation.py
- 兼容边界：保留当前默认不抛错，不在诊断中默认包含敏感原值；一次性源只消费一次。
- 正常验收：混合合法／非法数量得到正常结果和精确问题位置。
- 异常／边界：多字段同时错误、回调抛错、空源、重复迭代与缓存资源关闭明确。
- 原生回归：petl/test/transform/test_conversions.py；test_validation.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．流式 XML 行读取（增强提案）

- 来源／场景：[petl/io/xml.py:fromxml 的非流式说明](https://github.com/petl-developers/petl/blob/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b/petl/io/xml.py)
- 原版现状：现有 etree.parse 加载整个文档，注释明确 not streaming。
- 交付目标：新增 fromxmlstream，iterparse 在指定 row_tag 闭合时取出字段后清理节点。
- 影响模块：io/xml.py；io/sources.py
- 兼容边界：不改变原 fromxml 的任意 XPath 能力；流式首版支持受限相对路径并禁止外部实体。
- 正常验收：大量合成行 XML 逐行产生表，读取前几行不需等待整个文件。
- 异常／边界：嵌套同名行、命名空间、截断 XML、早停和流关闭；实测内存预算后才准入。
- 原生回归：petl/test/io/test_xml.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．Parquet 文件双向适配（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/627
- 原版现状：没有 fromparquet/toparquet，现有可选格式各自独立。
- 交付目标：增加可选 pyarrow extra，按 row group 读取／写入、显式 schema 与压缩参数。
- 影响模块：新增 io/parquet.py；io/__init__.py
- 兼容边界：核心不强制装 pyarrow；列类型不隐式 stringify，外部依赖成本须在此步单独实测。
- 正常验收：整数、文本、时间与空值表往返，列裁剪和分组写入生效。
- 异常／边界：依赖未安装、类型冲突、坏文件、空表与失败写入不发布半份目标。
- 原生回归：新增 Parquet 适配集合；petl/test/io/test_json.py 的表语义对照
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．多字段行索引的透视表（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/398
- 原版现状：pivot f1 仅按一个 flds.index 取列，不能直接按 region+gender 形成行键。
- 交付目标：允许 f1 为字段序列，构建复合行键与多个行头列。
- 影响模块：transform/reshape.py:PivotView/iterpivot
- 兼容边界：现有单字段调用保持；列维度与聚合函数顺序不变，不拆成多个测试步骤。
- 正常验收：region+gender 按 style 汇总 units，输出完整组合与缺失格。
- 异常／边界：复合键含 None、重复组合、多聚合值、空输入及 presorted 一致。
- 原生回归：petl/test/transform/test_reshape.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．笛卡尔积自定义字段前缀（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/296
- 原版现状：crossjoin 仅 prefix=True 生成1_/2_，没有按源指定业务前缀；Join 已有 lprefix/rprefix。
- 交付目标：增加 prefixes 序列，为 N 个输入显式指定前缀以避免 id 重名。
- 影响模块：transform/joins.py:CrossJoinView/itercrossjoin
- 兼容边界：布尔 prefix 保持；不能忽略多传 kwargs 假装功能已生效。
- 正常验收：订单和商品源输出 order_id/product_id，三表同理。
- 异常／边界：前缀长度不匹配、前缀冲突、None 前缀、空表与短行补齐。
- 原生回归：petl/test/transform/test_joins.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．作用域内临时目录和排序预算配置（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/389
- 原版现状：sort 可逐次传 tempdir，config 有 sort_buffersize，但各缓存／生成器临时文件无统一作用域配置。
- 交付目标：增加 etl.options 上下文，给新建视图注入默认 tempdir 与缓冲预算，退出恢复。
- 影响模块：config.py；transform/sorts.py；io/json.py 临时缓存
- 兼容边界：显式函数参数优先，不永久修改 tempfile.tempdir；现有全局 config 保持。
- 正常验收：作用域内排序溢写和字典生成器缓存只落指定临时目录。
- 异常／边界：嵌套恢复、异常退出、不可写目录、视图延迟执行的配置冻结规则明确。
- 原生回归：petl/test/transform/test_sorts.py；petl/test/io/test_json.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．作用域内 CSV 编码默认值（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/388
- 原版现状：fromcsv/tocsv 每次传 encoding/errors；config 没有 CSV 默认编码。
- 交付目标：扩展 options 接收 csv_encoding/csv_errors，视图创建时冻结有效配置。
- 影响模块：config.py；io/csv.py；io/csv_py3.py
- 兼容边界：默认仍走原平台编码，显式参数优先，不改变已经创建的视图。
- 正常验收：同批中文 CSV 读写共享 utf-8 配置，局部 override 可读其他编码。
- 异常／边界：嵌套、异常恢复、非法编码与错误策略、延迟迭代隔离。
- 原生回归：petl/test/io/test_csv.py
- 真实依赖：08

## 10．字段相等筛选的归一化键（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/384
- 原版现状：selecteq 只有 operator.eq，大小写不敏感需手写 select 回调。
- 交付目标：selecteq 增加可选 key/normalize，同样转换待比较值与字段。
- 影响模块：transform/selects.py:selecteq/selectop
- 兼容边界：默认严格相等；不自动把所有字符串都 lower 或改变数值比较。
- 正常验收：str.casefold 将 Straße/STRASSE 正确匹配，输出仍是原始值。
- 异常／边界：None、非字符串、自定义 key 抛错、complement 和缺失字段策略。
- 原生回归：petl/test/transform/test_selects.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．按业务键更新已有 SQL 行（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/128
- 原版现状：todb/appenddb 做加载与追加，没有原生按 key 更新目标已有行的 updatedb。
- 交付目标：增加 SQLite/DB-API 首版 updatedb，显式 keys、更新字段及未命中策略。
- 影响模块：io/db.py；io/db_create.py 既有类型／引用工具
- 兼容边界：默认不新增／删除记录，不改变 todb 默认 truncate；首版不宣称全部 SQL 方言适配。
- 正常验收：订单数值按 sku 更新并返回匹配数，非目标列保持。
- 异常／边界：缺键、复合键、重复源键、绑定错误和 commit=False 的调用者事务保持。
- 原生回归：petl/test/io/test_db.py；test_db_cursor_cleanup.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．数据库加载前的结构与存在性预检（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/397
- 原版现状：create/drop/truncate 控制已有，但未提供独立只读预检结果，错误可能在消费数据后才出现。
- 交付目标：新增 inspect_db_target，返回表存在、列对应、插入能力及计划中的破坏性动作。
- 影响模块：io/db.py；io/db_create.py
- 兼容边界：预检不执行 truncate/create/drop，也不能只靠一次检查承诺之后无并发变化。
- 正常验收：不存在／结构匹配／结构冲突三种 SQLite 目标得到准确摘要且源零消费。
- 异常／边界：带 schema 名、只读连接、权限不可查、缺字段与引用特殊表名。
- 原生回归：petl/test/io/test_db.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．字典源发现样本外字段的显式政策（增强提案）

- 来源／场景：[petl/io/json.py:fromdicts/DictsGeneratorView](https://github.com/petl-developers/petl/blob/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b/petl/io/json.py)
- 原版现状：只从前 sample 项发现 header，后续新键不会进入表，没有 warn/error 选项。
- 交付目标：增加 extras=ignore/warn/error，未知字段可携带行号报告，不静默误以为全部入表。
- 影响模块：io/json.py:DictsView/DictsGeneratorView/iterdicts
- 兼容边界：默认 ignore 保持；动态扩大已输出 header 不允许，需显式全量 schema 扫描。
- 正常验收：sample=1 后出现 currency，error 指出行和字段，显式 header 可包含它。
- 异常／边界：空源、生成器、字段次序、None 键与多次遍历一致，诊断不包含值。
- 原生回归：petl/test/io/test_json.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．CSV NUL 字节输入策略（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/565
- 原版现状：现代 Python csv 可保留 NUL，旧 issue 不能直接当当前缺陷；核心无统一 NUL policy。
- 交付目标：增加 null_bytes=preserve/error/drop 的显式输入适配，默认 preserve 对齐当前 Python。
- 影响模块：io/csv.py；io/csv_py3.py
- 兼容边界：不自动删字符；严格模式错误含逻辑行位置，避免只做字节替换破坏多字节编码。
- 正常验收：合成 NUL CSV 的三种政策结果明确，普通 CSV 字节语义不变。
- 异常／边界：引号内 NUL、多行记录、流式 source 与编码错误处理互不混淆。
- 原生回归：petl/test/io/test_csv.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．从文本直接提取命名正则字段（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/151
- 原版现状：现有 fromtext(...).capture(...) 两阶段可做，原入口不支持直接命名分组导表。
- 交付目标：新增 fromregex 组合入口，按命名分组形成 header，并显式 skip/error 不匹配行。
- 影响模块：io/text.py；transform/regex.py
- 兼容边界：复用既有正则和 source 机制，不自动执行表达式；fromtext strip 旧默认保持。
- 正常验收：日志行直接提取 timestamp/level/message，Unicode 和分组顺序明确。
- 异常／边界：可选组缺失、不匹配、零宽匹配、非法正则与超长行上限由调用者明确。
- 原生回归：petl/test/io/test_text.py；petl/test/transform/test_regex.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．按列顺序展开和还原数值流（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/79
- 原版现状：flatten/unflatten 文档只承诺 row-major，未提供列优先往返。
- 交付目标：增加 order=row/column，列优先模式接受明确表形状并控制临时缓存。
- 影响模块：transform/reshape.py:FlattenView/UnflattenView
- 兼容边界：默认 row 保持，列模式需二次访问的成本不能隐藏成纯流式。
- 正常验收：两行三列表列优先展开后按形状还原，header 与值对应。
- 异常／边界：短行 missing、长行、非整形数量、空表、一次性输入与临时资源关闭。
- 原生回归：petl/test/transform/test_reshape.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．结构化进度与取消检查（增强提案）

- 来源／场景：[petl/util/timing.py:progress/log_progress](https://github.com/petl-developers/petl/blob/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b/petl/util/timing.py)
- 原版现状：已有文本进度和 logger 输出，不能直接给程序消费 typed 事件或取消请求。
- 交付目标：增加 progress_events(callback,cancel_check)，含行数、耗时、批速率及完成标记。
- 影响模块：util/timing.py:ProgressViewBase
- 兼容边界：保留已有文本输出；取消异常与普通转换错误区分，不自动回滚已写外部数据库。
- 正常验收：批次事件单调增加，最后不足一批仍有完成事件，取消后源及时关闭。
- 异常／边界：空输入、回调抛错、早停、时钟回拨用单调时钟和取消间隔上限。
- 原生回归：petl/test/util/test_timing.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．可重新打开的持久表检查点（增强提案）

- 来源／场景：[petl/io/json.py:DictsGeneratorView 临时缓存](https://github.com/petl-developers/petl/blob/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b/petl/io/json.py)
- 原版现状：生成器内部临时 pickle 缓存仅对象生命周期内存在，缺少受控可恢复业务产物。
- 交付目标：新增 checkpoint(table,path,format)，发布原生 CSV/JSONL 加 schema 与摘要，随后只读重开。
- 影响模块：util/materialise.py；io/json.py；io/csv.py
- 兼容边界：不把不可信 pickle 文件作为跨会话接口；显式路径且不缓存凭据，默认不覆盖。
- 正常验收：转换中间表写检查点，另进程重开后继续 aggregate，类型策略按格式明确。
- 异常／边界：半写、摘要不符、源已变化、目标存在与未知格式拒绝，不伪造自动 exactly-once。
- 原生回归：petl/test/util/test_materialise.py；petl/test/io/test_jsonl.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．校验后同时分流合格表与问题行（增强提案）

- 来源／场景：[petl/transform/validation.py:validate](https://github.com/petl-developers/petl/blob/cd5ed9dd3ec1c95eb4c2285bcc71d945f7acb86b/petl/transform/validation.py)
- 原版现状：validate 只返回问题表；再读原表筛合格项对一次性源需自行缓存。
- 交付目标：新增 validate_split，将同一遍约束结果分为 good/bad/problem 三个可消费视图。
- 影响模块：transform/validation.py；io/json.py 缓存辅助
- 兼容边界：现有 validate 输出不改；分流缓存显式有界溢写，不把打印错误替代坏行隔离。
- 正常验收：订单合法行进入 good、坏行完整进入 bad，问题关联原行号。
- 异常／边界：一行多问题不重复计坏行、消费者先后顺序、异常和提前关闭释放缓存。
- 原生回归：petl/test/transform/test_validation.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．严格表达式模式拒绝静默降级（增强提案）

- 来源／场景：https://github.com/petl-developers/petl/issues/699
- 原版现状：trusted=False 缺 asteval 时退回 eval，且 _expr_impl 全局按首次调用冻结；已有有限限制不是无条件沙箱。
- 交付目标：新增明确 evaluator/require_safe，逐调用选择，安全依赖缺失即拒绝，定义受支持 AST 语法。
- 影响模块：util/base.py:expr/_safe_expr；transform/selects.py 与 conversions.py 透传
- 兼容边界：旧 trusted 默认暂保持并弃用提示；不以简单黑名单承诺任意 Python 安全，不对真实系统执行攻击。
- 正常验收：普通算术/字段比较可用，交错 trusted 调用不污染严格模式。
- 异常／边界：禁止属性逃逸／导入／危险调用的纯合成测试；缺依赖、深 AST 与错误位置明确。
- 原生回归：petl/test/util/test_base.py；test_selects.py；test_conversions.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
