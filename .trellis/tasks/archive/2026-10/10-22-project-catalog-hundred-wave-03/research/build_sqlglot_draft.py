"""制作公开SQL主仓的独立业务任务与有界血缘渲染修复。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """先冻结实际任务表，再生成材料和独立验收。@return None。"""
    rows = [
        ('SG-U01', 'understand', '区分SQL解析与数据库校验',
            'Parse SELECT missing FROM orders without a schema. Explain what a successful parse proves about syntax, table existence, column validity, execution permissions and safety. No edits and no external database.',
            'The pinned parser returns SELECT missing FROM orders successfully. This proves a syntactic AST was produced, not table/column existence, database permissions, successful execution or SQL safety. Schema-aware checks and the actual database contract are separate.',
            'parsing_does_not_validate_database_schema'),
        ('SG-U02', 'understand', '解释单语句接口的批次结果',
            'Compare parse_one("SELECT 1; SELECT 2") with parse of the same text. Explain the returned shapes and a caller boundary that requires exactly one statement. No edits.',
            'At this exact commit parse_one returns an exp.Block containing both statements;parse returns a two-element list. Do not assume parse_one discards the second statement. A single-statement boundary must explicitly validate the parsed statement count and allowed statement kinds before execution.',
            'parse_one_can_return_a_multi_statement_block'),
        ('SG-U03', 'understand', '解释重复输出名的血缘损失',
            'Call lineage(None,"SELECT quantity AS x, quantity + 1 AS x FROM orders",schema={"orders":{"quantity":"INT"}}). Compare the two select positions with the returned mapping. No edits.',
            'There are two output positions but one mapping key x. At this fixed commit its expression is orders.quantity AS x. A name-keyed mapping cannot faithfully identify both duplicate output positions. Require unique aliases for this workflow or design a separately authorized positional contract;do not invent an existing positional lineage API.',
            'duplicate_output_aliases_collapse_in_name_keyed_lineage'),
        ('SG-C01', 'consult', '保留跨方言集合运算语义',
            'Inspect SELECT 1 AS n UNION SELECT 2 AS n INTERSECT SELECT 3 AS n read as postgres and generated for sqlite. Compare executing the raw generated SQL,adding direct parentheses around the INTERSECT operand,and using SELECT 1 AS n UNION SELECT * FROM (SELECT 2 AS n INTERSECT SELECT 3 AS n). Recommend a bounded migration control;no library edits.',
            'The pinned AST is Intersect with a Union left operand;raw SQLite output returns an empty result although PostgreSQL precedence requires row1. Direct parenthesized SELECT operands generated here are rejected by SQLite. The supplied explicit derived-query form executes and returns[(1,)]. Preserve that verified grouping boundary and compare actual result sets;do not claim arbitrary dialect conversion is semantics-preserving or authorize a parser rewrite.',
            'set_precedence_requires_an_explicit_executable_sqlite_boundary'),
        ('SG-C02', 'consult', '处理空本地表的类型推断',
            'Execute SELECT quantity FROM orders using Table(columns=["quantity"],rows=[]) with no schema,then with schema={"orders":{"quantity":"INT"}}. Recommend the smallest compatible caller change;no library edits.',
            'The pinned automatic inference indexes the first row and raises IndexError for the empty table. Supplying the explicit INT schema yields an empty result successfully. Preserve column names/types as an ingestion contract and pass that schema;do not manufacture a row,swallow arbitrary failures or claim an empty SELECT must return NULL.',
            'empty_local_tables_require_an_explicit_schema_workaround'),
        ('SG-P01', 'plan', '规划可复现的本地报表对照',
            'Plan a finite local report for rows tea/2,coffee/1,tea/3 with columns product,quantity. Use SELECT product,SUM(quantity) AS total FROM orders GROUP BY product ORDER BY product. Compare SQLGlot Python execution with PostgreSQL-to-SQLite conversion executed in an in-memory SQLite database. No implementation or external service.',
            'Both supplied local paths return coffee/1 then tea/5. Plan fixed dialect/schema/input identity,parameterized loading,explicit output order,and expected rows/types. Include empty input,NULLs,duplicate names and set-operation counterexamples in a future regression matrix;distinguish this finite successful report from a universal cross-dialect guarantee.',
            'finite_report_matches_python_executor_and_sqlite_control')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change',
        'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('SG-D01', 'diagnose', '诊断筛选列未进入值血缘',
        'A report has a filter column missing from the displayed lineage. Request the exact SQL,schema,requested output and observed node names. Diagnose the existing contract without edits.',
        [], 'diagnosed_or_information_requested',
        'With the supplied evidence distinguish output value lineage from predicate/control influence. The filter-only product column is absent from quantity value lineage by the observed API contract. Missing SQL/schema/output/node evidence supports insufficient_information;do not fabricate a defect,claim the predicate has no business influence or implement another lineage contract.', None))
    materials['disclosure/filter-lineage.md'] = 'Observed call: lineage("quantity","SELECT quantity FROM orders WHERE product = \'tea\'",schema={"orders":{"quantity":"INT","product":"TEXT"}}). node.walk() names are quantity and orders.quantity. orders.product is absent. The requested quantity value is sourced from orders.quantity;the product predicate influences row selection. Only diagnose this evidence;no output API change is authorized.\n'
    materials['disclosure/unavailable.md'] = 'The exact SQL,schema,requested output and observed node names are unavailable.\n'
    answers.update({'SG-D01-question': 'Please provide the exact SQL,schema,requested output column and observed lineage node names. No edits are authorized.',
        'SG-D01': 'The supplied output is value lineage: quantity is sourced from orders.quantity. product only influences row selection through WHERE,so its absence from these value nodes does not mean it has no business effect. A separate predicate/control influence model would need its own contract and authorization. No changes were made.',
        'SG-D01-unavailable': 'The SQL,schema,requested output and observed node names are unavailable. Record insufficient_information and request that evidence later. The exact cause is unproven;no changes.'})
    materials['materials/render-repair.md'] = 'A report renders a lineage Node and later exports its source SQL. The pinned Node.to_html inserts exp.Tag into the original source with copy=False,so rendering contaminates SQL with <b> tags and repeated calls can nest highlights. Repair only library/sqlglot/lineage.py and app/test_lineage_render.py. Preserve every original source/expression tree,object identity and parent/arg_key/index relationship. Render a separate representation that still highlights the corresponding expression. Keep repeated labels/titles/edges stable for the same Node,shared sources,an expression that is itself the source,table nodes,dialect and GraphHTML options. Do not disable highlighting,change other APIs or touch original tests/private controls/dependencies. Deliver meaningful public tests that fail on the pinned original and pass after the repair. HTML browser execution and external JavaScript downloads are outside this task.\n'
    definitions.append(('SG-M01', 'modify', '修复血缘图展示污染原SQL',
        'Implement the supplied bounded lineage rendering repair and public regression tests. Only the two authorized files may change.',
        ['materials/render-repair.md'], 'repaired_and_regression_verified',
        'Render without mutating any original AST or parent links. Keep the corresponding expression highlighted,repeatable graph data,shared-source/root/table cases and existing dialect/options behavior. Deliver meaningful public regressions and preserve the full original public-main suite;merely setting transform(copy=True) loses identity-based highlighting and is insufficient.',
        ['rendering_preserves_ast_and_parent_links', 'highlights_target_and_remains_repeatable',
            'shared_sources_and_root_expression_remain_valid']))
    materials['seed/app/test_lineage_render.py'] = '"""请在授权修复中补充血缘图渲染的公开回归测试。"""\n'
    answers['SG-M01'] = 'Repaired library/sqlglot/lineage.py to render a copied source while locating the corresponding copied expression,so original ASTs and parent links remain intact and highlighting stays valid. Added six public regressions in app/test_lineage_render.py for repeated rendering,highlighting,shared sources,root expressions,table nodes and dialect/options. All original controls are preserved.'
    build_project('sqlglot', {'title': 'SQLGlot查询与血缘工作场景', 'category': 'SQL解析、转换与报表血缘',
        'description': '公开主仓的解析边界、转换对照、空表方案、重复输出名、血缘诊断和图渲染修复。'},
        definitions,
        [('SG-S01', '解析边界', '区分语法、语句批次与执行合同', ['SG-U01', 'SG-U02']),
         ('SG-S02', '方言与输入兼容', '用实际执行对照转换和空表行为', ['SG-C01', 'SG-C02']),
         ('SG-S03', '报表与输出合同', '规划有限报表并核对重复输出名', ['SG-P01', 'SG-U03']),
         ('SG-S04', '筛选影响诊断', '区分值来源与筛选影响', ['SG-D01']),
         ('SG-S05', '血缘展示修复', '保持原查询和有效高亮', ['SG-M01'])], materials,
        modifications={'SG-M01': ['library/sqlglot/lineage.py', 'app/test_lineage_render.py']},
        branches={'SG-D01': [{'id': 'filter-lineage-evidence',
            'when': 'Exact SQL,schema,requested output and observed node names have not been supplied or declared unavailable and are reasonably requested.',
            'materials': ['disclosure/filter-lineage.md']}]},
        extra_entries={'SG-S04': [{'id': 'unavailable', 'task_ids': ['SG-D01'],
            'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/LICENSE', 'seed/library/tests/fixtures/jsonpath/LICENSE'])
    Path(__file__).with_name('sqlglot-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
