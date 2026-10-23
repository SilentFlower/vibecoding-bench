# PyPika：二十步真实工程迭代路线

固定 [kayak/pypika@465fb9ae12f7727d28785d087b64e6226da5714e](https://github.com/kayak/pypika/tree/465fb9ae12f7727d28785d087b64e6226da5714e)，见[单仓审查](./pypika.md)。9项已复现修复提案与11项明确增强；本轮仅研究，未实施，拟议新API不能当现版入口。

原生业务基线实际运行内存SQLite。其他方言的当前证据为原版生成SQL+源码与官方语法核对，未连接PostgreSQL/MySQL/Snowflake/ClickHouse；未来引擎解析/业务效果与锁行为需单独隔离验收，不能用字符串断言冒充。每步包含实现、测试、文档和失败修复，不拆矩阵凑数。

## 01．负微秒时间间隔保留符号

- **类型与来源**：原版复现修复提案；时间报表构造仅含负微秒的Interval，需与负秒一致。
- **原版现状与证据**：01_negative_microseconds：microseconds=-1输出正的1 MICROSECOND，seconds=-1保留负号；构造器已保存is_negative，但专门分支不使用。
- **交付目标**：修正微秒单单位分支的符号应用，所有支持的dialect模板使用同一正确有符号表达式。
- **影响模块**：pypika/terms.py。
- **兼容边界**：正微秒、零、混合单位、周/季度现有行为不变；不对不同单位符号做未经定义的归一化。
- **正常验收**：-1微秒得到INTERVAL负1，正1仍为正，且反复序列化一致。
- **边界验收**：大数、0、与seconds混用、各dialect引用模板与源Interval不变性回归。
- **原生回归**：pypika/tests/test_date_math.py。
- **实际依赖**：无；标准库，纯SQL文本生成。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/3526)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 02．EXISTS投影保留别名

- **类型与来源**：原版复现修复提案；商品报表把EXISTS子查询投影为has_products，需要结果列名稳定。
- **原版现状与证据**：02_exists_alias：as_(has_products)已记录alias，但SELECT EXISTS(...)没有别名；ExistsCriterion.get_sql没调用format_alias_sql。
- **交付目标**：在with_alias语境给EXISTS/NOT EXISTS正确应用alias，区分WHERE条件不带别名。
- **影响模块**：pypika/terms.py。
- **兼容边界**：未加别名输出与WHERE行为不变；不把子查询内部别名错误提升为外层别名。
- **正常验收**：SELECT中的has_products出现一次，WHERE EXISTS无输出列别名。
- **边界验收**：NOT EXISTS、quoted别名、嵌套投影、不同quote_char与子查询返回列回归。
- **原生回归**：pypika/tests/test_criterions.py、pypika/tests/test_selects.py。
- **实际依赖**：无；复用现有format_alias_sql。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/819)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 03．方言不支持的索引提示明确拒绝

- **类型与来源**：原版复现修复提案；PostgreSQL业务查询误用MySQL索引提示，编译时应报告不支持而非输出不可用方言语句。
- **原版现状与证据**：03_dialect_index_hints：PostgreSQLQuery生成FORCE INDEX/USE INDEX；当前两方法在通用QueryBuilder，无方言能力验证。官方PostgreSQL SELECT语法没有这些子句。
- **交付目标**：将提示支持纳入方言契约；MySQL继续生成，PostgreSQL等不支持方言在构造/序列化明确DialectNotSupported，不静默丢业务意图。
- **影响模块**：pypika/queries.py、pypika/dialects.py、pypika/utils.py。
- **兼容边界**：通用Query历史兼容策略需明确；不强制把所有提示转成普通注释，不自动改写为数据库设置。
- **正常验收**：MySQL提示生成保持，PostgreSQL相同请求给准确不支持错误。
- **边界验收**：多个提示、空列表、已命名索引、子查询与copy后的builder不互相污染。
- **原生回归**：pypika/tests/test_selects.py、pypika/tests/dialects/test_mysql.py、pypika/tests/dialects/test_postgresql.py。
- **实际依赖**：无；不连接数据库；未来引擎集成测试可另准备PostgreSQL/MySQL。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/3521)；[依据2](https://www.postgresql.org/docs/18/sql-select.html)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)；[依据5](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/utils.py)。

## 04．空PostgreSQL语句不追加孤立后缀

- **类型与来源**：原版复现修复提案；条件更新没有实际set时，builder原本返回空字符串；附加returning不应变成残缺语句。
- **原版现状与证据**：04_empty_postgres_statement：空update返回空串，加returning变成单独RETURNING，空insert加on_conflict变成单独ON CONFLICT。
- **交付目标**：PostgreSQLQueryBuilder.get_sql在基础语句为空时保持空结果，不附加returning/conflict；统一明确空builder行为。
- **影响模块**：pypika/dialects.py、pypika/queries.py。
- **兼容边界**：保留通用QueryBuilder空串约定；正常有值insert/update的后缀不变，不把空更新自动变成SELECT。
- **正常验收**：三类反例都得到空串，真正set/insert后得到完整带后缀语句。
- **边界验收**：returning star、do_nothing、do_update、where和copy构造不改变原builder；重复get_sql无副作用。
- **原生回归**：pypika/tests/dialects/test_postgresql.py、pypika/tests/test_updates.py、pypika/tests/test_inserts.py。
- **实际依赖**：无；只改SQL构造。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/832)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)。

## 05．嵌套CTE的冲突目标不泄漏命名空间

- **类型与来源**：原版复现修复提案；带join的外层报表引用插入CTE，内部ON CONFLICT和EXCLUDED列需要遵守各自语法。
- **原版现状与证据**：05_upsert_namespace：单独upsert列正确；放入有join的WITH后出现ON CONFLICT(products.id)、SET products.quantity=EXCLUDED.products.quantity。外层with_namespace透传影响PG专用后缀。
- **交付目标**：隔离冲突目标、SET左值和EXCLUDED右值的命名空间规则，内部生成不受外层join需要影响；保留值表达式真实外表引用。
- **影响模块**：pypika/dialects.py、pypika/queries.py。
- **兼容边界**：不能统一关闭所有字段命名空间；SELECT来源/WHERE/RETURNING仍按各自上下文输出。
- **正常验收**：同一upsert单独与嵌入CTE时后缀语法一致，target为id且EXCLUDED只限定一次。
- **边界验收**：多冲突列、别名、显式表达式更新、on_conflict条件、do_update条件和多层CTE各有回归。
- **原生回归**：pypika/tests/dialects/test_postgresql.py、pypika/tests/test_inserts.py。
- **实际依赖**：无；已对照官方INSERT语法；未运行PostgreSQL服务。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/3520)；[依据2](https://www.postgresql.org/docs/18/sql-insert.html)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)。

## 06．DELETE USING保留已声明CTE

- **类型与来源**：原版复现修复提案；业务清理查询从old_rows CTE引用待处理编号，SQL文本需要包含WITH定义。
- **原版现状与证据**：06_delete_with_cte：已with_(subquery,old_rows)，最终只输出DELETE...USING old_rows，没有WITH定义；delete分支未拼接_with_sql。
- **交付目标**：为DELETE分支生成前置WITH，与SELECT/UPDATE/INSERT一致，保持USING位置和别名。
- **影响模块**：pypika/queries.py、pypika/dialects.py。
- **兼容边界**：普通不带WITH的DELETE输出不变；不改变数据操作条件或自动执行语句。
- **正常验收**：反例输出以WITH old_rows AS(...)开头，并保留DELETE FROM/USING/WHERE顺序。
- **边界验收**：多个CTE、returning、嵌套子查询、CTE名引用与普通USING表、immutable复制均回归。
- **原生回归**：pypika/tests/test_deletes.py、pypika/tests/dialects/test_postgresql.py。
- **实际依赖**：无；纯本地构造；未来数据库效果需独立沙箱验证。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/756)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)。

## 07．函数参数继承序列化上下文

- **类型与来源**：原版复现修复提案；报表工具给普通ABS参数收集绑定值时，函数内值应和直接值一致。
- **原版现状与证据**：07_function_kwargs：Function(ABS,-2)传QmarkParameter仍生成ABS(-2)，收集参数为空；直接ValueWrapper传相同类型会生成?。Function.get_sql丢弃剩余kwargs。
- **交付目标**：把parameter等剩余受支持上下文完整传给get_function_sql和内部参数，避免重复或丢失关键字。
- **影响模块**：pypika/terms.py。
- **兼容边界**：默认非参数化SQL不变；quote_char/dialect/schema/alias仍只有一份明确值，不让自定义Function收到重复参数。
- **正常验收**：ABS(-2)生成ABS(?)且参数[-2]，嵌套函数与WHERE常量参数次序正确。
- **边界验收**：多个参数、同一参数对象、aggregate/filter、schema函数、custom function及自定义序列化上下文回归。
- **原生回归**：pypika/tests/test_functions.py、pypika/tests/test_parameter.py、pypika/tests/test_custom_functions.py。
- **实际依赖**：无；使用现有Parameter体系，不新增驱动依赖。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/791)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 08．组合表达式判空保留优先级

- **类型与来源**：原版复现修复提案；业务条件结果本身可能为NULL，isnull应作用于整个组合表达式。
- **原版现状与证据**：08_null_precedence：输出id=1 AND quantity=2 IS NULL，缺整体括号；内存SQLite对NULL=1 AND 2=2 IS NULL得到0，而整体加括号得到1。
- **交付目标**：NullCriterion/NotNullCriterion按被包装表达式优先级添加必要括号，保持整个term的判空语义。
- **影响模块**：pypika/terms.py。
- **兼容边界**：简单field IS NULL输出可保持；不依靠字符串检测AND/OR，使用表达式类型/precedence；已有Bracket手工替代继续可用。
- **正常验收**：组合AND/OR条件判空输出分组，SQLite合成真值与显式括号一致。
- **边界验收**：算术、函数、比较、嵌套Not、alias、isnotnull与SQL三值逻辑回归，不改变原criterion对象。
- **原生回归**：pypika/tests/test_criterions.py、pypika/tests/test_negation.py。
- **实际依赖**：无；标准库sqlite3只用于本轮效果对照。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/724)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 09．可连续组合的JSON值表达式

- **类型与来源**：增强提案；业务JSON数组位于对象内部，需连续get_json_value后contains。
- **原版现状与证据**：09_json_chaining：get_json_value返回BasicCriterion，该对象没有contains，实际AttributeError；可手工BasicCriterion(JSONOperators.CONTAINS,...)替代。
- **交付目标**：区分JSON值表达式与布尔JSON判据，值读取后继续支持JSON路径/contains等合法操作，并保留明确优先级。
- **影响模块**：pypika/terms.py、pypika/enums.py。
- **兼容边界**：现有Field JSON运算生成保持；get_text_value返回文本后不误提供JSON操作；不能直接把所有BasicCriterion混入JSON。
- **正常验收**：payload->array_key再contains列表产生正确嵌套表达式，三层取值可继续组合。
- **边界验收**：整数数组索引、缺失路径表达式、文本读取、别名、否定与括号优先级回归；不声称对真实JSON数据已执行。
- **原生回归**：pypika/tests/dialects/test_postgresql.py、pypika/tests/test_criterions.py。
- **实际依赖**：无；使用现有JSONTerms；未来PG JSONB执行测试需要独立数据库。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/806)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/enums.py)。

## 10．当前日期时间的关键字语法

- **类型与来源**：原版复现修复提案；PostgreSQL查询投影当前日期/时间，与已正确的CURRENT_TIMESTAMP保持一致。
- **原版现状与证据**：10_current_date_time：CurDate/CurTime生成CURRENT_DATE()/CURRENT_TIME()，CurTimestamp已省括号；官方日期时间语法给出无参关键字形式。
- **交付目标**：按方言实现当前日期/时间关键字生成，CurDate/CurTime采用目标方言支持的形式，可选精度另作明确参数。
- **影响模块**：pypika/functions.py。
- **兼容边界**：其他普通函数调用保留括号；不同数据库接受形式需按dialect处理，不全局替换所有函数名。
- **正常验收**：PostgreSQL生成CURRENT_DATE,CURRENT_TIME,CURRENT_TIMESTAMP，未加别名和有别名均正确。
- **边界验收**：显式时间精度、未知dialect、字段同名、quote_char和旧函数测试回归。
- **原生回归**：pypika/tests/test_functions.py、pypika/tests/dialects/test_postgresql.py。
- **实际依赖**：无；已对照官方文档；未声称运行PG时间查询。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/809)；[依据2](https://www.postgresql.org/docs/18/functions-datetime.html)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/functions.py)。

## 11．明确的Python切片分页入口

- **类型与来源**：增强提案；商品列表取第2至4项时，需要长度为2并明确不支持负索引/步长。
- **原版现状与证据**：11_slice_semantics：q[2:4]生成LIMIT4 OFFSET2，负数直接OFFSET-2，步长被忽略。现有slice等价设置offset/limit，已有显式limit/offset替代。
- **交付目标**：新增明确python_slice/slice_range入口或版本化切片模式，将stop-start转limit并校验边界，对负数/非1步长明确拒绝或单独定义。
- **影响模块**：pypika/queries.py。
- **兼容边界**：不默默改变旧[]用户的limit解释；提供迁移说明，普通limit/offset保持。
- **正常验收**：新模式[2:4]等价limit2 offset2，空范围输出明确空结果策略，原builder不变。
- **边界验收**：省略start/stop、start大于stop、负数、布尔/非整数、步长和方言分页差异回归。
- **原生回归**：pypika/tests/test_selects.py、pypika/tests/test_query.py。
- **实际依赖**：无；纯分页生成。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/731)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)。

## 12．显式NULL排序位置

- **类型与来源**：增强提案；商品报表要把缺失数量排在最后，与升降序独立。
- **原版现状与证据**：12_nulls_ordering：传nulls=LAST与普通orderby输出相同；orderby只保存(field,order)，没有NULLS策略。
- **交付目标**：增加每个排序项的nulls_first/nulls_last契约，按支持方言输出NULLS FIRST/LAST，不支持方言明确拒绝或显式模拟。
- **影响模块**：pypika/queries.py、pypika/terms.py、pypika/enums.py。
- **兼容边界**：未传时原排序不变；方向与空值位置分别定义；不静默替用户增加额外排序键。
- **正常验收**：PG两字段分别ASC NULLS LAST及DESC NULLS FIRST，保留顺序与alias解析。
- **边界验收**：相互冲突选项、函数表达式、analytic orderby、UNION排序及不支持方言有明确行为。
- **原生回归**：pypika/tests/test_selects.py、pypika/tests/test_analytic_queries.py。
- **实际依赖**：无；官方SELECT语法为依据；其他方言集成后续另验证。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/797)；[依据2](https://www.postgresql.org/docs/18/sql-select.html)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)；[依据5](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/enums.py)。

## 13．受支持方言的共享行锁子句

- **类型与来源**：增强提案；事务业务需要表达FOR SHARE/KEY SHARE，与现有FOR UPDATE区分。
- **原版现状与证据**：13_for_share：类方法无for_share，for_update可生成既有语句；没有原生共享锁选择。
- **交付目标**：提供锁模式枚举/for_share入口，支持OF、NOWAIT/SKIP LOCKED的方言组合验证。
- **影响模块**：pypika/dialects.py、pypika/queries.py、pypika/enums.py。
- **兼容边界**：现有for_update输出与默认行为保持；同查询冲突锁模式明确拒绝，不自动开启事务或连接数据库。
- **正常验收**：PG生成FOR SHARE/KEY SHARE及指定OF关系的完整子句。
- **边界验收**：互斥等待选项、重复调用、子查询、UNION限制与不支持dialect明确报错；未来锁行为不能仅靠字符串断言证明。
- **原生回归**：pypika/tests/dialects/test_postgresql.py、pypika/tests/dialects/test_mysql.py。
- **实际依赖**：无新运行包；未来共享锁行为验收需隔离数据库连接，本轮未进行。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/822)；[依据2](https://www.postgresql.org/docs/18/sql-select.html)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据5](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/enums.py)。

## 14．结构化UNPIVOT表表达式

- **类型与来源**：增强提案；宽表月度指标需要生成metric/value长表查询文本。
- **原版现状与证据**：14_unpivot：QueryBuilder类无unpivot；当前只能LiteralValue或自定义Selectable手工拼接。
- **交付目标**：为支持方言增加UNPIVOT可选择表表达式，显式值列、名称列、源列与null处理选项，支持后续select/filter。
- **影响模块**：pypika/queries.py、pypika/dialects.py、pypika/terms.py。
- **兼容边界**：普通FROM/JOIN不变；不在不支持方言默默输出，源列标识符走现有quoting。
- **正常验收**：四个月度列生成UNPIVOT(value FOR metric IN(...))且外层字段引用正确。
- **边界验收**：空源列、重复列、名称冲突、别名、include/exclude null及多次嵌套操作有清晰契约。
- **原生回归**：pypika/tests/dialects/test_snowflake.py、pypika/tests/test_selects.py。
- **实际依赖**：无；未来数据库解析/效果测试需对应方言环境，不算本轮通过。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/830)；[依据2](https://docs.snowflake.com/en/sql-reference/constructs/unpivot)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)；[依据5](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 15．通配投影排除指定列

- **类型与来源**：增强提案；分析报表需要选择全部业务列但去掉大型内部字段，不先查询表结构。
- **原版现状与证据**：15_star_exclusions：Star没有exclude方法，SnowflakeQuery只能SELECT *；现有替代是应用显式列举所有列。
- **交付目标**：增加Star.except_/exclude结构，按不同dialect输出EXCEPT或EXCLUDE，并与qualified star和replace策略区分。
- **影响模块**：pypika/terms.py、pypika/queries.py、pypika/dialects.py。
- **兼容边界**：原Star与_select_star去重规则保持；只支持明确方言，不能把数据库EXCEPT集合运算混为投影排除。
- **正常验收**：Snowflake/指定支持方言生成合法* EXCLUDE(列)并保留外层表别名。
- **边界验收**：空排除集、重复名称、quoted列、qualified star、select混合表达式及不支持方言明确处理。
- **原生回归**：pypika/tests/test_selects.py、pypika/tests/dialects/test_snowflake.py。
- **实际依赖**：无；数据库实际列展开效果待后续隔离引擎验证。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/726)；[依据2](https://docs.snowflake.com/en/sql-reference/sql/select)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据5](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)。

## 16．ClickHouse建表的引擎与排序契约

- **类型与来源**：增强提案；分析应用需要生成MergeTree类建表文本，声明引擎、分区与排序键。
- **原版现状与证据**：16_clickhouse_create_options：ClickHouseQuery.create_table仍返回通用CreateQueryBuilder，只输出列；无engine/partition_by方法。
- **交付目标**：增加ClickHouse专用CreateQueryBuilder，支持结构化engine参数、partition_by/order_by/primary_key与TTL等明确选项，保留通用列约束。
- **影响模块**：pypika/dialects.py、pypika/queries.py。
- **兼容边界**：其他dialect建表不变；必要选项缺失应报错，不自动臆造引擎或排序键；TTL只作为同一建表能力参数，不拆步。
- **正常验收**：固定MergeTree普通表生成列、ENGINE、PARTITION BY、ORDER BY正确顺序与表达式。
- **边界验收**：空引擎、重复选项、表达式排序键、无分区、旧通用create/drop及immutable复制回归。
- **原生回归**：pypika/tests/dialects/test_clickhouse.py、pypika/tests/test_create.py。
- **实际依赖**：无新运行包；ClickHouse真实创建/检查是未来独立可选服务验收，不在本轮执行。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/766)；[依据2](https://clickhouse.com/docs/sql-reference/statements/create/table)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/dialects.py)；[依据4](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)。

## 17．条件链式构造助手

- **类型与来源**：增强提案；报表有可选筛选和join，开发者希望保持一条构造链并避免false分支副作用。
- **原版现状与证据**：17_conditional_chain：无QueryBuilder.when，但pipe已能调用自定义函数，不能把函数组合本身当新增。
- **交付目标**：增加when(condition,callback)的受支持助手，条件false不执行callback；true返回合法builder，保证copy约定。
- **影响模块**：pypika/queries.py、pypika/utils.py。
- **兼容边界**：现有pipe保持；不直接复用Case.when语义，避免名字含义混淆；immutable=False模式需明示副作用边界。
- **正常验收**：true加入商品数量过滤，false生成与原链完全一致SQL且callback调用次数0。
- **边界验收**：callback抛错/返回错误类型、可选join、嵌套when、alias与多次复用原链不串状态。
- **原生回归**：pypika/tests/test_immutability.py、pypika/tests/test_query.py、pypika/tests/test_joins.py。
- **实际依赖**：无；已有builder装饰器。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/857)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/utils.py)。

## 18．只读查询结构元数据

- **类型与来源**：增强提案；报表配置界面要查看所有来源表、join与投影字段，避免依赖私有_from/_joins。
- **原版现状与证据**：18_introspection：QueryBuilder.fields_故意返回[]以隔离子查询，tables_也为空；is_joined只回答指定表；没有metadata属性。不能修改fields_的既有内部语义充当新功能。
- **交付目标**：新增只读metadata访问器，显式区分当前作用域与递归子查询，返回来源/join类型/选择项/别名及真实字段引用。
- **影响模块**：pypika/queries.py、pypika/terms.py。
- **兼容边界**：fields_/nodes_和现有验证逻辑保持；结果不可修改builder；不声称自动推导数据库血缘或星号展开列。
- **正常验收**：左右两表join均出现在metadata来源，投影字段带正确所属和别名，当前/递归作用域可区分。
- **边界验收**：CTE、重复表别名、派生表、聚合、union、表达式与self join不会重复或循环；顺序稳定。
- **原生回归**：pypika/tests/test_internals.py、pypika/tests/test_joins.py、pypika/tests/test_immutability.py。
- **实际依赖**：无；可独立交付，不要求步骤19别名去重。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/786)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 19．可选择的投影别名去重与映射

- **类型与来源**：增强提案；用户组合报表字段时两个value别名需要稳定结果列映射。
- **原版现状与证据**：19_alias_deduplication：原版可输出两个value，无deduplicate_aliases；重复列名本身并非所有数据库的语法错误，不能直接按缺陷处理。
- **交付目标**：提供opt-in别名去重器，返回新查询和每个投影项的最终别名映射，用稳定后缀避开已占用名称。
- **影响模块**：pypika/queries.py、pypika/terms.py。
- **兼容边界**：默认严格保留用户别名；不在默认生成时偷偷改名；GROUP/ORDER/HAVING的别名引用需明确按投影身份解析，含糊引用报错。
- **正常验收**：两个value变value/value_1，原Field.alias不变，返回映射与真实输出列一致。
- **边界验收**：已有value_1、多次相同Field、函数/聚合、quoted大小写、union对应列和嵌套scope分别确定，不能循环加后缀。
- **原生回归**：pypika/tests/test_selects.py、pypika/tests/test_immutability.py、pypika/tests/test_query.py。
- **实际依赖**：无；与metadata共享内部遍历可复用，但不构成强制功能步骤依赖。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/856)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/queries.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)。

## 20．通用IS与IS NOT比较表达式

- **类型与来源**：增强提案；本地业务布尔和NULL比较需要明确IS TRUE/IS NOT FALSE，而非只提供等号或IS NULL。
- **原版现状与证据**：20_is_comparison：Term类无is_/is_not；isnull现有，普通布尔相等生成=id true形式。当前可自定义Comparator/BasicCriterion。
- **交付目标**：增加明确IS/IS NOT判据，约束可接受右操作数与方言语法，支持NULL/TRUE/FALSE及相应表达式。
- **影响模块**：pypika/terms.py、pypika/enums.py。
- **兼容边界**：isnull/isnotnull和==语义保持；不把Python对象身份比较is自动重载为SQL。
- **正常验收**：field.is_(True)、is_not(False)、is_(None)生成指定语句，SQLite普通真值样本可实际对照。
- **边界验收**：复杂左表达式括号、别名、unsupported RHS、not操作和不同dialect保留明确行为。
- **原生回归**：pypika/tests/test_criterions.py、pypika/tests/test_negation.py。
- **实际依赖**：无；SQLite效果验收可用标准库，本轮新API尚未实施。 功能步骤依赖：无。
- **源码及原始来源**：[依据1](https://github.com/kayak/pypika/issues/840)；[依据2](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/terms.py)；[依据3](https://github.com/kayak/pypika/blob/465fb9ae12f7727d28785d087b64e6226da5714e/pypika/enums.py)。

## 独立验收与累计回归

未来控制端冻结原生PyPika API构造场景和正常/边界预期，核对候选加载路径、生成SQL、参数集合、metadata、复制不变性及相应隔离数据库效果。每步必须运行关联原生测试与此前已接受用例，不能通过删除测试或只声明新方法放行。当前1099主测试及90子测试通过不证明本路线已实施；冻结用例、离线依赖准备与平台原生接入均未完成。
