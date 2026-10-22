# sqlglot实际场景任务表

固定来源：https://github.com/tobymao/sqlglot@67961afbed7c986dfe26ab82db89a25814c1bdcb。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## SG-U01：区分SQL解析与数据库校验

类型：understand；合法结果：explained。

用户问题与当前控制：Parse SELECT missing FROM orders without a schema. Explain what a successful parse proves about syntax, table existence, column validity, execution permissions and safety. No edits and no external database.

独立验收：The pinned parser returns SELECT missing FROM orders successfully. This proves a syntactic AST was produced, not table/column existence, database permissions, successful execution or SQL safety. Schema-aware checks and the actual database contract are separate.

公开材料：materials/sg-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：parsing_does_not_validate_database_schema。

## SG-U02：解释单语句接口的批次结果

类型：understand；合法结果：explained。

用户问题与当前控制：Compare parse_one("SELECT 1; SELECT 2") with parse of the same text. Explain the returned shapes and a caller boundary that requires exactly one statement. No edits.

独立验收：At this exact commit parse_one returns an exp.Block containing both statements;parse returns a two-element list. Do not assume parse_one discards the second statement. A single-statement boundary must explicitly validate the parsed statement count and allowed statement kinds before execution.

公开材料：materials/sg-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：parse_one_can_return_a_multi_statement_block。

## SG-U03：解释重复输出名的血缘损失

类型：understand；合法结果：explained。

用户问题与当前控制：Call lineage(None,"SELECT quantity AS x, quantity + 1 AS x FROM orders",schema={"orders":{"quantity":"INT"}}). Compare the two select positions with the returned mapping. No edits.

独立验收：There are two output positions but one mapping key x. At this fixed commit its expression is orders.quantity AS x. A name-keyed mapping cannot faithfully identify both duplicate output positions. Require unique aliases for this workflow or design a separately authorized positional contract;do not invent an existing positional lineage API.

公开材料：materials/sg-u03.md

授权：只读，不产生接受代码检查点。

实际业务控制：duplicate_output_aliases_collapse_in_name_keyed_lineage。

## SG-C01：保留跨方言集合运算语义

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Inspect SELECT 1 AS n UNION SELECT 2 AS n INTERSECT SELECT 3 AS n read as postgres and generated for sqlite. Compare executing the raw generated SQL,adding direct parentheses around the INTERSECT operand,and using SELECT 1 AS n UNION SELECT * FROM (SELECT 2 AS n INTERSECT SELECT 3 AS n). Recommend a bounded migration control;no library edits.

独立验收：The pinned AST is Intersect with a Union left operand;raw SQLite output returns an empty result although PostgreSQL precedence requires row1. Direct parenthesized SELECT operands generated here are rejected by SQLite. The supplied explicit derived-query form executes and returns[(1,)]. Preserve that verified grouping boundary and compare actual result sets;do not claim arbitrary dialect conversion is semantics-preserving or authorize a parser rewrite.

公开材料：materials/sg-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：set_precedence_requires_an_explicit_executable_sqlite_boundary。

## SG-C02：处理空本地表的类型推断

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Execute SELECT quantity FROM orders using Table(columns=["quantity"],rows=[]) with no schema,then with schema={"orders":{"quantity":"INT"}}. Recommend the smallest compatible caller change;no library edits.

独立验收：The pinned automatic inference indexes the first row and raises IndexError for the empty table. Supplying the explicit INT schema yields an empty result successfully. Preserve column names/types as an ingestion contract and pass that schema;do not manufacture a row,swallow arbitrary failures or claim an empty SELECT must return NULL.

公开材料：materials/sg-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：empty_local_tables_require_an_explicit_schema_workaround。

## SG-P01：规划可复现的本地报表对照

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：Plan a finite local report for rows tea/2,coffee/1,tea/3 with columns product,quantity. Use SELECT product,SUM(quantity) AS total FROM orders GROUP BY product ORDER BY product. Compare SQLGlot Python execution with PostgreSQL-to-SQLite conversion executed in an in-memory SQLite database. No implementation or external service.

独立验收：Both supplied local paths return coffee/1 then tea/5. Plan fixed dialect/schema/input identity,parameterized loading,explicit output order,and expected rows/types. Include empty input,NULLs,duplicate names and set-operation counterexamples in a future regression matrix;distinguish this finite successful report from a universal cross-dialect guarantee.

公开材料：materials/sg-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：finite_report_matches_python_executor_and_sqlite_control。

## SG-D01：诊断筛选列未进入值血缘

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A report has a filter column missing from the displayed lineage. Request the exact SQL,schema,requested output and observed node names. Diagnose the existing contract without edits.

独立验收：With the supplied evidence distinguish output value lineage from predicate/control influence. The filter-only product column is absent from quantity value lineage by the observed API contract. Missing SQL/schema/output/node evidence supports insufficient_information;do not fabricate a defect,claim the predicate has no business influence or implement another lineage contract.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

## SG-M01：修复血缘图展示污染原SQL

类型：modify；合法结果：repaired_and_regression_verified。

用户问题与当前控制：Implement the supplied bounded lineage rendering repair and public regression tests. Only the two authorized files may change.

独立验收：Render without mutating any original AST or parent links. Keep the corresponding expression highlighted,repeatable graph data,shared-source/root/table cases and existing dialect/options behavior. Deliver meaningful public regressions and preserve the full original public-main suite;merely setting transform(copy=True) loses identity-based highlighting and is insufficient.

公开材料：materials/render-repair.md

授权：仅修改library/sqlglot/lineage.py、app/test_lineage_render.py。

实际业务控制：rendering_preserves_ast_and_parent_links、highlights_target_and_remains_repeatable、shared_sources_and_root_expression_remain_valid。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
