"""观察固定候选的解析、转换、报表和血缘渲染业务行为。"""
import json
import os
from pathlib import Path
import sqlite3
import sys

import sqlglot
from sqlglot import exp, parse, parse_one, transpile
from sqlglot.executor import execute
from sqlglot.executor.table import Table
from sqlglot.lineage import Node, lineage


def tree_state(root: Node) -> str:
    """冻结原图的树内容与父指针。@param root 原血缘根。@return 稳定状态文本。"""
    return json.dumps([{'name': node.name, 'source': node.source.dump(),
        'expression': node.expression.dump(),
        'parents': [(id(part), id(part.parent) if part.parent is not None else None,
            part.arg_key, part.index) for part in node.source.walk()]}
        for node in root.walk()], sort_keys=True)


def rendering_checks() -> dict:
    """覆盖普通、共享源码和根表达式，不能用失去高亮换取不变异。@return 独立结果。"""
    root = lineage('total', 'SELECT quantity + 1 AS total FROM orders',
        schema={'orders': {'quantity': 'INT'}}, trim_selects=False)
    before = tree_state(root)
    highlighted = '<b>' + root.expression.sql(pretty=True) + '</b>'
    first, second = root.to_html(imports=False), root.to_html(imports=False)
    intact = tree_state(root) == before
    repeated = first.nodes == second.nodes and first.edges == second.edges
    highlighted_once = (highlighted in first.nodes[id(root)]['title']
        and first.nodes[id(root)]['title'].count('<b>') == 1)
    source = parse_one('SELECT x AS first, x + 1 AS second FROM input')
    child = Node('second', source.expressions[1], source)
    shared = Node('first', source.expressions[0], source, downstream=[child])
    shared_before = tree_state(shared)
    shared_graph = shared.to_html(imports=False)
    shared_ok = (tree_state(shared) == shared_before and len(shared_graph.nodes) == 2
        and all(shared_graph.nodes[id(node)]['title'].count('<b>') == 1 for node in shared.walk()))
    expression = parse_one('x + 1')
    only = Node('result', expression, expression)
    only_before = tree_state(only)
    only_graph = only.to_html(imports=False)
    root_ok = tree_state(only) == only_before and '<b>x + 1</b>' in only_graph.nodes[id(only)]['title']
    return {'rendering_preserves_ast_and_parent_links': intact,
        'highlights_target_and_remains_repeatable': highlighted_once and repeated,
        'shared_sources_and_root_expression_remain_valid': shared_ok and root_ok}


def main() -> None:
    """按真实任务执行独立控制。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(sqlglot.__file__).resolve() == root / 'library/sqlglot/__init__.py'}
    task = sys.argv[1]
    if task == 'SG-U01':
        tree = parse_one('SELECT missing FROM orders')
        result['parsing_does_not_validate_database_schema'] = (
            isinstance(tree, exp.Select) and tree.sql() == 'SELECT missing FROM orders')
    elif task == 'SG-U02':
        block = parse_one('SELECT 1; SELECT 2')
        result['parse_one_can_return_a_multi_statement_block'] = (
            isinstance(block, exp.Block) and len(block.expressions) == 2
            and len(parse('SELECT 1; SELECT 2')) == 2)
    elif task == 'SG-U03':
        nodes = lineage(None, 'SELECT quantity AS x, quantity + 1 AS x FROM orders',
            schema={'orders': {'quantity': 'INT'}})
        result['duplicate_output_aliases_collapse_in_name_keyed_lineage'] = (
            list(nodes) == ['x'] and nodes['x'].expression.sql() == 'orders.quantity AS x')
    elif task == 'SG-C01':
        query = 'SELECT 1 AS n UNION SELECT 2 AS n INTERSECT SELECT 3 AS n'
        tree = parse_one(query, read='postgres')
        with sqlite3.connect(':memory:') as database:
            raw = database.execute(tree.sql('sqlite')).fetchall()
            parenthesized = transpile('SELECT 1 AS n UNION (SELECT 2 AS n INTERSECT SELECT 3 AS n)',
                read='postgres', write='sqlite')[0]
            try:
                database.execute(parenthesized)
                parentheses_rejected = False
            except sqlite3.OperationalError:
                parentheses_rejected = True
            grouped = database.execute(
                'SELECT 1 AS n UNION SELECT * FROM (SELECT 2 AS n INTERSECT SELECT 3 AS n)').fetchall()
        result['set_precedence_requires_an_explicit_executable_sqlite_boundary'] = (
            isinstance(tree, exp.Intersect) and isinstance(tree.this, exp.Union)
            and raw == [] and parentheses_rejected and grouped == [(1,)])
    elif task == 'SG-C02':
        empty = Table(columns=['quantity'], rows=[])
        try:
            execute('SELECT quantity FROM orders', tables={'orders': empty})
            missing_schema_error = False
        except IndexError:
            missing_schema_error = True
        explicit = execute('SELECT quantity FROM orders', schema={'orders': {'quantity': 'INT'}},
            tables={'orders': Table(columns=['quantity'], rows=[])})
        result['empty_local_tables_require_an_explicit_schema_workaround'] = missing_schema_error and explicit.rows == []
    elif task == 'SG-P01':
        query = 'SELECT product, SUM(quantity) AS total FROM orders GROUP BY product ORDER BY product'
        rows = [{'product': 'tea', 'quantity': 2}, {'product': 'coffee', 'quantity': 1},
            {'product': 'tea', 'quantity': 3}]
        python_result = execute(query, tables={'orders': rows})
        with sqlite3.connect(':memory:') as database:
            database.execute('CREATE TABLE orders(product TEXT, quantity INTEGER)')
            database.executemany('INSERT INTO orders VALUES (:product, :quantity)', rows)
            sqlite_result = database.execute(transpile(query, read='postgres', write='sqlite')[0]).fetchall()
        result['finite_report_matches_python_executor_and_sqlite_control'] = (
            python_result.columns == ('product', 'total')
            and python_result.rows == sqlite_result == [('coffee', 1), ('tea', 5)])
    elif task == 'SG-M01':
        result.update(rendering_checks())
    else:
        raise ValueError('未知SQLGlot控制任务')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
