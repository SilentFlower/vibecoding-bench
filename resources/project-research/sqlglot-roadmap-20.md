# SQLGlot 二十步迭代研究路线

固定[tobymao/sqlglot@67961afbed7c986dfe26ab82db89a25814c1bdcb](https://github.com/tobymao/sqlglot/tree/67961afbed7c986dfe26ab82db89a25814c1bdcb)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已存在：方言读写、parse_one多语句Block、Parser.max_nodes预算、结构化ParseError、Token位置信息、全部输出列血缘lineage(None)/on_node.payload、AST dump/load、AST diff、Optimizer自定义rules、UDF schema类型、DDL rename构建器、replace_tables/replace_placeholders、sources展开、anonymize、Table迭代与执行器LIMIT早停；以上均未重复列作新增。FAQ明确解析宽松且不是数据库validator、格式不完全保真，这些已声明行为不当作缺陷。

## 01．集合运算跨方言转换保持源方言优先级

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobymao/sqlglot/issues/8390)、[来源](https://github.com/tobymao/sqlglot/pull/8704)、[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/parser.py)；报表将Postgres的UNION与INTERSECT混合查询转为SQLite本地执行。
- **原版现状／替代**：固定原版把SELECT 1 UNION SELECT 2 INTERSECT SELECT 3解析成Intersect(Union(...),...)；转SQLite实跑为空，按Postgres优先级明确分组应返回1。上游issue8390与尚未合并的PR8704提供同根因来源。
- **交付与模块**：让解析树记录源方言的集合优先级，生成目标方言可表达的显式分组；SQLite不能接受的直接操作数括号使用合法派生查询。；`sqlglot/parser.py`、`sqlglot/generator.py`、`sqlglot/dialects/dialect.py`、`sqlglot/generators/sqlite.py`。
- **兼容边界**：不同方言对INTERSECT优先级并不相同；保留显式括号、ALL/DISTINCT与ORDER/LIMIT归属，不能统一采用Postgres规则。
- **正常验收**：该查询Postgres解析树语义正确，转SQLite执行返回1，反向等优先级输入也保留原结果。
- **异常／边界验收**：UNION/EXCEPT长链、混合ALL、已有子查询、末尾ORDER/LIMIT和嵌套分组；对不支持的结构按现有unsupported规则报告。
- **原生回归**：`tests/test_parser.py`、`tests/dialects/test_dialect.py`、`tests/dialects/test_sqlite.py`、`tests/test_executor.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 02．血缘图渲染保持原节点源码不变

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/lineage.py)；本地报表先展示血缘图，再导出原SQL，或重复渲染同一Node。
- **原版现状／替代**：to_html用copy=False把exp.Tag写回Node.source；实跑首次源SQL出现<b>，第二次嵌套<b><b>。输入lineage默认复制并不能保护其返回Node后续不被渲染污染。
- **交付与模块**：用独立渲染副本或非变异高亮生成方式，保持Node.source、expression和父子关系，重复渲染给出相同SQL标签。；`sqlglot/lineage.py`、`sqlglot/expressions/core.py`。
- **兼容边界**：保留GraphHTML现有节点/边字段及调用选项；只消除展示对研究对象的副作用，不改变现有lineage copy参数含义。
- **正常验收**：渲染前后source.dump、expression.sql完全相同，连续两次图的标签和title等价。
- **异常／边界验收**：共享下游DAG、多输出、trim_selects两模式、已有Tag、图生成异常与sources展开；不依赖随机内存id比较输出。
- **原生回归**：`tests/test_lineage.py`、`tests/test_expressions.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 03．空本地表的自动schema推断给出有效结果或明确诊断

- **类型／来源与场景**：bug_fix；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/executor/__init__.py)；日报当天没有订单，但调用者已用Table声明quantity列，仍用可选schema默认值执行普通SELECT。
- **原版现状／替代**：execute在schema缺省时无条件table[0][column]；实跑已声明列的空表抛IndexError，传显式INT schema则返回空结果。
- **交付与模块**：处理有列无行的推断路径：可执行的投影保留列名并返回空行，必须知道类型的运算采用明确UNKNOWN策略或ExecuteError，消除内部越界。；`sqlglot/executor/__init__.py`、`sqlglot/executor/table.py`、`sqlglot/optimizer/annotate_types.py`。
- **兼容边界**：不凭空猜列类型，不把空list且完全没有列定义当成已知表结构；显式schema始终优先。
- **正常验收**：Table(columns=[quantity],rows=[])执行SELECT quantity FROM orders返回quantity列和零行，不再IndexError。
- **异常／边界验收**：空表聚合COUNT、无列空表、多个表中一个为空、全部值为NULL、未知类型函数和显式schema冲突；现有非空表推断不回退。
- **原生回归**：`tests/test_executor.py`、`tests/test_schema.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 04．方言转换返回带位置与规则编码的诊断结果

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/generator.py)；本地SQL迁移工具要逐条列出哪些属性或函数被降级，供报表维护者决定是否接受。
- **原版现状／替代**：已有unsupported_level与Generator.unsupported_messages字符串列表；实跑HIVE ROW FORMAT转Postgres移除该属性，只留下字符串提示。ParseError已有结构化errors，并非所有诊断都缺结构。
- **交付与模块**：增加可选转换结果对象，含SQL、稳定诊断code、严重度、源节点/位置、源目标方言与降级说明。；`sqlglot/generator.py`、`sqlglot/errors.py`、`sqlglot/__init__.py`。
- **兼容边界**：默认transpile仍返回list[str]，保留WARN/RAISE/IGNORE语义；不把没有报错等同于数据库可执行性保证。
- **正常验收**：同一不支持属性返回一个定位到源属性的诊断，SQL与原默认生成一致；严格模式仍拒绝。
- **异常／边界验收**：一节点多个降级、重复节点、无位置的程序构树、自定义dialect、unknown函数和诊断截断；code独立于人类提示文本。
- **原生回归**：`tests/test_generator.py`、`tests/test_transpile.py`、`tests/test_errors.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 05．生成SQL可提供到原SQL的片段映射

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/generator.py)；用户在转换后的报表SQL中选择一列，希望定位原脚本对应表达式。
- **原版现状／替代**：Token和部分Identifier/函数已有start/end元数据，根Select位置可能为空；生成器目前只返回字符串，没有输出片段到输入区间的source map。
- **交付与模块**：新增显式generate_with_map结果，跟踪生成字符区间、源AST路径及可用输入区间，并标明合成/重写节点。；`sqlglot/generator.py`、`sqlglot/expressions/core.py`、`sqlglot/tokenizer_core.py`。
- **兼容边界**：现有元数据不是完整保真CST；映射可多对多，无法确定来源时明确无映射，不虚构位置。
- **正常验收**：带中文标识符与换行SQL转换后，用户选择输出列片段可映射回正确输入区间，输出SQL不变。
- **异常／边界验收**：一个函数展开多个目标片段、注释移动、引用符变化、Unicode字符/字节口径、程序构树和优化删除节点。
- **原生回归**：`tests/test_generator.py`、`tests/test_tokens.py`、`tests/test_expressions.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 06．脚本解析逐语句保留成功树与错误记录

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/parser.py)；本地SQL编辑器同时展示三条语句，其中第二条尚未写完，仍希望分析第一与第三条。
- **原版现状／替代**：parse严格模式在第二条抛ParseError；IGNORE实跑返回SELECT FROM等不完整树但没有逐条状态，WARN只有日志，缺少带原区间的统一结果。
- **交付与模块**：提供parse_results脚本入口，返回语句序号、源区间、成功AST或结构化错误，定义可恢复的分号边界。；`sqlglot/parser.py`、`sqlglot/__init__.py`、`sqlglot/errors.py`、`sqlglot/tokenizer_core.py`。
- **兼容边界**：不把容错树当有效SQL；默认parse行为保持；字符串/过程体内分号不得误切，词法错误无法安全恢复时明确终止剩余。
- **正常验收**：SELECT 1;SELECT FROM;SELECT 3返回成功、错误、成功三项并有原始行号。
- **异常／边界验收**：空语句、注释、引号内分号、未闭字符串、块语句、嵌套过程和源dialect差异；每条状态与实际错误一致。
- **原生回归**：`tests/test_parser.py`、`tests/test_errors.py`、`tests/test_tokens.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 07．查询输出提供按位置组织的字段描述

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/optimizer/annotate_types.py)；报表导出前展示列名、推断类型、来源和未知项，让调用者定义输出契约。
- **原版现状／替代**：annotate_types/optimize已能为投影推断类型，selects可遍历；实跑product为TEXT、total为INT。没有高层describe_query返回稳定逐列描述。
- **交付与模块**：提供查询描述入口，按ordinal保留重复/无名字段，含展示名、推断类型、已知可空性及unknown原因。；`sqlglot/optimizer/annotate_types.py`、`sqlglot/optimizer/qualify.py`、`sqlglot/schema.py`、`sqlglot/expressions/query.py`。
- **兼容边界**：不重复实现已有类型推断，不调用真实数据库；schema不足时UNKNOWN，不能冒称完整数据库校验或确定非空。
- **正常验收**：已知schema的星展开、计算列和UNION返回有序字段，字段描述与selects一致。
- **异常／边界验收**：重复别名、匿名表达式、外连接可空、UDF未知类型、STRUCT字段、空schema和不支持DML输出；不悄悄合并同名列。
- **原生回归**：`tests/test_optimizer.py`、`tests/test_schema.py`、`tests/test_typing.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 08．血缘边区分值来源与筛选影响

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/lineage.py)；业务解释quantity报表时，除了数值来自quantity，还要显示product筛选决定哪些行进入结果。
- **原版现状／替代**：现有lineage为投影值来源建图；SELECT quantity WHERE product=tea实跑仅quantity与orders.quantity节点，product只留在source SQL。
- **交付与模块**：增加可选影响血缘模式，为WHERE/HAVING/JOIN/GROUP/窗口条件建立带角色的边，保留原值来源边。；`sqlglot/lineage.py`、`sqlglot/optimizer/scope.py`、`sqlglot/optimizer/qualify.py`。
- **兼容边界**：默认列值血缘保持；明确数据值贡献与控制行集合的影响不同，不声称能判定谓词必然改变某条数据。
- **正常验收**：筛选列以filter角色连接，quantity仍为value角色；连接键和聚合分组分别可辨。
- **异常／边界验收**：相关子查询、EXISTS、窗口PARTITION/ORDER、常量输出、重复引用与CTE遮蔽；只读分析不变异输入。
- **原生回归**：`tests/test_lineage.py`、`tests/test_optimizer.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 09．血缘公开入口可按输出位置追踪重复别名

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/lineage.py)；两个报表投影都命名x，但它们来自不同计算，客户端按列序号读取。
- **原版现状／替代**：lineage(None)返回dict[str,Node]，实跑两个x仅剩一个键且落到首个表达式；公开column仅str/Column/None，内部集合分支虽按int传递但非公开位置入口。
- **交付与模块**：新增ordinal选择与有序多列结果模式，节点身份包含作用域和输出位置，支持同名及匿名投影。；`sqlglot/lineage.py`、`sqlglot/expressions/query.py`。
- **兼容边界**：保留按名查询与默认dict兼容规则；不要把现有name字典承诺解释为必然保留重名。
- **正常验收**：SELECT quantity AS x,quantity+1 AS x按0和1得到不同表达式，两项均保留，UNION按位置续接。
- **异常／边界验收**：负/越界索引、空投影、星展开后位置、CTE列名列表、同名列不同scope及按名歧义策略。
- **原生回归**：`tests/test_lineage.py`、`tests/test_expressions.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 10．血缘图可导出稳定且可往返的本地JSON

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/lineage.py)；报表版本间保存血缘图，在另一个进程读取并比较，无需HTML或浏览器。
- **原版现状／替代**：Node有walk/to_html和payload；GraphHTML节点id使用id(node)，AST本身虽已有dump/load，Node DAG没有公开稳定JSON协议。
- **交付与模块**：增加版本化DAG编解码，保存稳定节点标识、边、表达式/来源和可JSON化payload，并按引用恢复共享下游。；`sqlglot/lineage.py`、`sqlglot/serde.py`。
- **兼容边界**：不重复计已有AST序列化或GraphHTML.nodes字典；未知版本/自定义payload策略明确，稳定性定义不依赖进程内地址。
- **正常验收**：同一输入在两个进程导出字节级稳定，往返后walk、节点角色和共享节点拓扑一致。
- **异常／边界验收**：重复子图、递归/循环引用防护、非JSON payload、重复ID、悬空边、无source_name及schema版本迁移。
- **原生回归**：`tests/test_lineage.py`、`tests/test_serde.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 11．优化器可解释逐规则改写过程

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/optimizer/optimizer.py)；维护者比较报表优化前后，需知道哪条规则删除CTE或下推谓词，而不只看最终SQL。
- **原版现状／替代**：optimize已有自定义rules/copy及SQL错误高亮，返回最终AST；循环中不提供标准事件、各规则快照或耗时记录。局部journal用于内部回滚，并非用户改写历史。
- **交付与模块**：新增可选trace回调/结果，记录规则名、前后结构摘要、改写状态和耗时，支持按需保留快照。；`sqlglot/optimizer/optimizer.py`、`sqlglot/optimizer/journal.py`。
- **兼容边界**：默认不保留大树历史；不能把未改变AST称跳过规则，用户自定义规则失败仍按原异常传播且带最后事件。
- **正常验收**：两条明确规则的trace顺序一致，可定位首次结构变化，最终结果与普通optimize一致。
- **异常／边界验收**：原地规则、新根规则、无变化、异常、callback异常、复制策略、快照上限和相同规则多次调用。
- **原生回归**：`tests/test_optimizer.py`、`tests/test_expressions.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 12．schema重命名可按作用域改写查询引用

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/expressions/builders.py)；普通订单表把quantity改为qty后，批量更新自有报表，保留无关CTE同名字段。
- **原版现状／替代**：已有rename_column/table只构造ALTER DDL；replace_tables可按表名替换，transform可手写遍历，没有按解析scope解析对象身份并检查冲突的引用迁移入口。
- **交付与模块**：提供显式schema映射驱动的rename_references，解析物理表/列与别名，重写相关引用并输出歧义/冲突预览。；`sqlglot/expressions/builders.py`、`sqlglot/optimizer/scope.py`、`sqlglot/optimizer/qualify.py`、`sqlglot/schema.py`。
- **兼容边界**：不执行DDL、不连接数据库；默认保留报表输出别名，未确认schema不能猜测未限定列归属；支持dry-run。
- **正常验收**：别名o.quantity和相关子查询正确改为o.qty，另一张表或CTE里的quantity不变。
- **异常／边界验收**：引用大小写、带引号名称、表别名遮蔽、USING/NATURAL JOIN、星投影、STRUCT同名字段与新名字冲突。
- **原生回归**：`tests/test_optimizer.py`、`tests/test_transforms.py`、`tests/test_build.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 13．常量可提取为目标方言占位符与绑定值

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/expressions/builders.py)；本地报表缓存SQL模板，同时把筛选日期和金额保存为独立绑定数据。
- **原版现状／替代**：replace_placeholders已有把参数替换进AST的能力；anonymize用于替换标识符/数字/字符串且不返回原值绑定表，不能代替语义保留的反向参数提取。
- **交付与模块**：增加显式parameterize入口，按表达式上下文提取可绑定literal，返回SQL/AST与有序或命名参数以及原类型。；`sqlglot/expressions/builders.py`、`sqlglot/generator.py`、`sqlglot/anonymize.py`。
- **兼容边界**：不手工拼SQL，不把表名/类型名/ORDER BY序号误当参数；方言禁止绑定的LIMIT/DDL位置默认保留或明确拒绝。
- **正常验收**：WHERE quantity>2 AND product=tea提取两项，交给本地sqlite参数执行与原查询结果一致。
- **异常／边界验收**：NULL/布尔/负数/日期/Decimal、重复常量合并策略、问号样式差异、字符串内冒号、数组与现有参数混用。
- **原生回归**：`tests/test_build.py`、`tests/test_generator.py`、`tests/test_transpile.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 14．SQL差异可按报表语义生成变更说明

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/diff.py)；评审者要快速识别新版本改变筛选阈值还是新增输出，低层AST编辑对象不便直接展示。
- **原版现状／替代**：diff已有Insert/Remove/Move/Update/Keep与delta_only，实跑得到Insert/Move集合，没有投影、条件、连接、聚合粒度等报表语义分组。
- **交付与模块**：增加semantic_diff高层摘要，映射到输出位置/作用域，分类展示投影、筛选、连接及分组/排序变化并关联低层节点。；`sqlglot/diff.py`、`sqlglot/optimizer/scope.py`、`sqlglot/expressions/query.py`。
- **兼容边界**：这是结构变更解释，不能把结果称为完整SQL等价证明；单纯格式/大小写按方言规范化策略处理。
- **正常验收**：数量阈值1改2报告filter变更，新增total报告projection变更，不分裂成几十条叶子插入。
- **异常／边界验收**：别名重命名、投影调序、子查询迁移、AND次序、UNION重组及未知函数；匹配置信不足明确标注。
- **原生回归**：`tests/test_diff.py`、`tests/test_optimizer.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 15．离线DDL脚本可演进版本化schema快照

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/schema.py)；本地迁移预览仅给CREATE/ALTER/DROP文件，需算出后续报表分析所用schema，不启动数据库。
- **原版现状／替代**：Parser已有DDL表达式，MappingSchema可add_table/copy/get_column_type；实跑ALTER解析为Alter，没有将DDL应用到schema的公开入口。
- **交付与模块**：新增显式apply_ddl/SchemaSnapshot工具，支持声明的表/列创建删除重命名与类型修改，逐语句产生新快照和不支持动作诊断。；`sqlglot/schema.py`、`sqlglot/expressions/ddl.py`、`sqlglot/expressions/query.py`。
- **兼容边界**：只模拟受支持的schema动作，不执行数据迁移/DDL；不静默忽略未知ALTER，不假装支持数据库所有依赖与默认值语义。
- **正常验收**：CREATE orders(quantity INT)后ADD product TEXT产生两列快照，旧快照不变，后续查询能按新schema解析。
- **异常／边界验收**：IF EXISTS/IF NOT EXISTS、同名冲突、多动作ALTER、事务失败回滚、带catalog名字、依赖视图与方言类型别名。
- **原生回归**：`tests/test_schema.py`、`tests/test_parser.py`、`tests/test_build.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 16．schema变化可比较报表输出契约

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/optimizer/annotate_types.py)；底层列从INT改TEXT或星投影增加列时，报表消费者希望提前得到兼容性差异。
- **原版现状／替代**：可分别qualify/annotate_types再手工比selects，但没有将两份输出描述按序号/明确键比较并给unknown结论的契约检查器。
- **交付与模块**：基于第7步字段描述比较旧/新schema下的输出，报告新增/删除/重排、类型变化及已知可空性变化，由调用者指定容许策略。；`sqlglot/optimizer/annotate_types.py`、`sqlglot/schema.py`、`sqlglot/optimizer/qualify.py`。
- **兼容边界**：不把所有扩宽类型自动称安全，不模拟真实数据转换；unknown与确定不兼容分开，默认保留原查询与schema。
- **正常验收**：quantity由INT改TEXT时标出total类型契约改变；新增未被显式投影的列不影响SELECT quantity。
- **异常／边界验收**：SELECT *、重复列名、未知UDF、UNION类型变化、不同dialect类型等价、nullable未知与输出调序。
- **原生回归**：`tests/test_optimizer.py`、`tests/test_schema.py`、`tests/test_typing.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；[7]。

## 17．命名本地查询集可导出依赖顺序与循环说明

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/expressions/builders.py)；自有报表以sources字典组织daily与report，需确定变动影响哪些报表以及分析顺序。
- **原版现状／替代**：exp.expand和lineage(sources=...)已能展开查询来源，Scope区分CTE/表，但没有保留命名查询边的catalog依赖与拓扑报告。
- **交付与模块**：提供source_dependencies，按物理表与命名查询身份生成依赖DAG、拓扑层级、未解析外部表与明确循环路径。；`sqlglot/expressions/builders.py`、`sqlglot/optimizer/scope.py`、`sqlglot/lineage.py`。
- **兼容边界**：仅分析显式传入的本地查询，不发现远程对象；CTE同名应遮蔽catalog名，递归CTE和跨查询循环区别报告。
- **正常验收**：report依赖daily、daily依赖orders，输出daily先于report，反向影响查询能找到report。
- **异常／边界验收**：自依赖、两查询循环、重复schema名、嵌套CTE遮蔽、大小写引用、解析失败和未提供的外部表。
- **原生回归**：`tests/test_optimizer.py`、`tests/test_lineage.py`、`tests/test_build.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 18．查询可生成带策略版本的持久指纹

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/expressions/core.py)；本地报表目录按结构模板去重，希望常量不同的查询可归为同一模板，并在不同进程保持稳定。
- **原版现状／替代**：AST相等比较和hash已有，optimize可生成规范树，anonymize有定长token别名；没有声明方言/字面值/别名策略和版本的稳定持久fingerprint协议。
- **交付与模块**：基于第13步参数提取，增加显式规范化策略与稳定摘要，返回策略版本、方言和指纹，可选择保留或消去常量值。；`sqlglot/expressions/core.py`、`sqlglot/optimizer/optimizer.py`、`sqlglot/serde.py`。
- **兼容边界**：指纹表示所选结构规则相同，不证明SQL语义等价；默认不交换非交换运算、不合并潜在易变函数，也不使用Python进程hash作持久键。
- **正常验收**：相同方言下仅空白大小写不同的查询跨进程指纹相同；模板模式下筛选常量变化相同，投影列变化不同。
- **异常／边界验收**：带引号大小写、NaN/Decimal、参数类型、别名策略、dialect差异、策略升级、注释hint语义和哈希碰撞回查。
- **原生回归**：`tests/test_expressions.py`、`tests/test_optimizer.py`、`tests/test_serde.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；[13]。

## 19．本地执行器可按批次产生适用查询结果

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/executor/__init__.py)；桌面导出大量订单投影时，希望消费者先处理首批并可提前停止，避免结果rows整表驻留。
- **原版现状／替代**：execute返回Table且rows为list；Table已有迭代、执行器已有LIMIT及部分早停，并不是缺迭代方法。尚无从执行计划贯通到输出的批次协议。
- **交付与模块**：新增execute_batches，先支持明确可流水的scan/filter/project/limit，定义需物化的sort/join/aggregate处理与消费者close清理。；`sqlglot/executor/__init__.py`、`sqlglot/executor/python.py`、`sqlglot/executor/table.py`、`sqlglot/planner.py`。
- **兼容边界**：现有execute物化接口保持；不声称所有SQL可常量内存执行。需物化阶段可显式拒绝或使用受控预算，绝不静默丢数据。
- **正常验收**：可流水查询在遍历全部输入前交出首批，合并批次与原execute逐值一致，提前close停止后续扫描。
- **异常／边界验收**：空结果、批大小0/负、异常中断、LIMIT/OFFSET、需排序/聚合、NULL与重复行、不可重用输入迭代器。
- **原生回归**：`tests/test_executor.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；无。

## 20．命令行可逐文件输出结构化转换结果

- **类型／来源与场景**：enhancement；[来源](https://github.com/tobymao/sqlglot/blob/67961afbed7c986dfe26ab82db89a25814c1bdcb/sqlglot/__main__.py)；本地报表目录批量从一个方言转另一个，需知道每个文件和语句的结果与错误，适合脚本消费。
- **原版现状／替代**：python -m sqlglot已有单个sql参数、stdin、read/write、parse/tokenize和错误级别；没有多文件输入与JSONL结果/明确分隔、文件级错误继续策略。
- **交付与模块**：增加显式本地文件批处理与JSONL模式，使用第4/6步诊断和逐语句结果，输出文件名、语句序号、SQL和状态，定义退出码与原子写入。；`sqlglot/__main__.py`、`sqlglot/__init__.py`、`sqlglot/errors.py`。
- **兼容边界**：默认单SQL/stdin展示保持；仅处理明确本地路径，不下载或执行SQL。诊断走结构化记录，stdout不得混入额外日志破坏JSONL。
- **正常验收**：两个文件三个语句各有一行JSON，成功项转换正确，错误项定位准确；选择继续模式时其他项照常输出且总退出码非零。
- **异常／边界验收**：带空格/中文路径、文件不可读、UTF8错误、空文件、输出同名覆盖、原子写失败、stdin与文件冲突及未知dialect。
- **原生回归**：`tests/test_transpile.py`、`tests/test_parser.py`、`tests/test_errors.py`。
- **实际依赖／步骤依赖**：默认纯Python运行无需额外包或服务；本地完整测试实际安装duckdb1.5.6、pandas3.0.6、numpy2.5.4、python-dateutil2.9.0.post0、pytz2026.5、typing_extensions4.16.0与six1.17.0；测试构建行为另需setuptools84.2.1，按上游开发依赖范围解析并保存精确freeze。；[4, 6]。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
