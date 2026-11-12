"""沿CSVkit真实工具类观察投影、匹配、类型与本地查询。"""
from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import csvkit
from csvkit.utilities.csvcut import CSVCut
from csvkit.utilities.csvgrep import CSVGrep
from csvkit.utilities.csvsort import CSVSort
from csvkit.utilities.csvsql import CSVSQL


def invoke(tool, arguments: list[str]) -> str:
    """运行原工具和实际参数，恢复测试进程的异常输出钩子。@param tool 已核工具类。@param arguments 参数。@return 真输出。"""
    output, errors = StringIO(), StringIO()
    hook = sys.excepthook
    try:
        utility = tool(args=arguments, output_file=output, error_file=errors)
        utility.run()
        return output.getvalue()
    finally:
        sys.excepthook = hook


def rows(text: str) -> list:
    """按CSV语义读取实际输出。@param text 输出正文。@return 行列表。"""
    return list(csv.reader(StringIO(text)))


def projections() -> dict:
    """核投影保持CSV结构，删除空行发生在投影之后。@return 投影事实。"""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / 'orders.csv'
        source.write_text('id,note,amount\n001,"tea, green",2\n002,"line1\nline2",10\n')
        original = source.read_bytes()
        output = rows(invoke(CSVCut, ['-c', 'note,id', str(source)]))
        short = root / 'short.csv'
        short.write_text('id,a,b\nA,keep,\nB,,\nC,x\n')
        blank = rows(invoke(CSVCut, ['-c', 'b', str(short)]))
        removed = rows(invoke(CSVCut, ['-c', 'b', '-x', str(short)]))
        selected = rows(invoke(CSVCut, ['-c', 'a', '-x', str(short)]))
        unchanged = source.read_bytes() == original
    return {'quoted_projection_preserves_cells_and_identifiers': output
            == [['note', 'id'], ['tea, green', '001'], ['line1\nline2', '002']] and unchanged,
        'delete_empty_rows_uses_projected_cells_and_pads_short_rows': blank == [['b'], [''], [''], ['']]
            and removed == [['b']] and selected == [['a'], ['keep'], ['x']]}
def matching() -> dict:
    """核子串、精确名单及多列ALL／ANY。@return 匹配事实。"""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / 'sku.csv'
        source.write_text('sku\nAB\nXAB\nABC\n')
        matchfile = root / 'approved.txt'
        matchfile.write_text('AB\n')
        substring = rows(invoke(CSVGrep, ['-c', 'sku', '-m', 'AB', str(source)]))
        exact = rows(invoke(CSVGrep, ['-c', 'sku', '-f', str(matchfile), str(source)]))
        regex = rows(invoke(CSVGrep, ['-c', 'sku', '-r', '^AB$', str(source)]))
        multi = root / 'multi.csv'
        multi.write_text('id,status,note\nA,hit,miss\nB,miss,hit\nC,hit,hit\n')
        all_columns = rows(invoke(CSVGrep, ['-c', 'status,note', '-m', 'hit', str(multi)]))
        any_column = rows(invoke(CSVGrep, ['-c', 'status,note', '-m', 'hit', '-a', str(multi)]))
    return {'match_is_substring_while_file_and_anchored_regex_are_exact': substring == [['sku'], ['AB'], ['XAB'], ['ABC']]
            and exact == regex == [['sku'], ['AB']],
        'multiple_columns_default_to_all_and_any_is_explicit': [row[0] for row in all_columns[1:]] == ['C']
            and [row[0] for row in any_column[1:]] == ['A', 'B', 'C']}


def sort_types() -> dict:
    """核数值排序、全字符串模式和保真参数的区别。@return 排序事实。"""
    with TemporaryDirectory() as directory:
        source = Path(directory) / 'sort.csv'
        source.write_text('id,amount,note\n001,2,NA\n002,10,keep\n')
        original = source.read_bytes()
        numeric = rows(invoke(CSVSort, ['-c', 'amount', '-y', '0', str(source)]))
        lexical = rows(invoke(CSVSort, ['-c', 'amount', '-y', '0', '-I', '--blanks', str(source)]))
        preserved = rows(invoke(CSVSort, ['-c', 'amount', '-y', '0', '--no-leading-zeroes', '--blanks', str(source)]))
        unchanged = source.read_bytes() == original
    return {'numeric_and_no_inference_sort_have_different_order': [row[1] for row in numeric[1:]] == ['2', '10']
            and [row[1] for row in lexical[1:]] == ['10', '2'],
        'leading_zero_and_blank_policies_preserve_business_text': preserved[1] == ['001', '2', 'NA']
            and numeric[1] == ['1', '2', ''] and lexical[1] == ['002', '10', 'keep'] and unchanged}


def local_sql() -> dict:
    """只生成DDL或在工具自己的SQLite内存库执行固定合成查询。@return 本地SQL事实。"""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / 'sales.csv'
        source.write_text('region,amount\neast,2.50\neast,2.50\nwest,1.25\n')
        before = source.read_bytes()
        ddl = invoke(CSVSQL, ['-i', 'sqlite', '-y', '0', '--tables', 'sales', str(source)])
        after_ddl = sorted(path.name for path in root.iterdir()) == ['sales.csv']
        output = rows(invoke(CSVSQL, ['-y', '0', '--tables', 'sales',
            '--query', 'SELECT COUNT(*) AS n FROM sales',
            '--query', 'SELECT region, SUM(amount) AS total FROM sales GROUP BY region ORDER BY region', str(source)]))
        after_query = source.read_bytes() == before and sorted(path.name for path in root.iterdir()) == ['sales.csv']
    return {'dialect_only_outputs_schema_without_importing_data': 'CREATE TABLE sales' in ddl
            and 'INSERT INTO' not in ddl and after_ddl,
        'query_without_database_uses_memory_and_outputs_last_result': output[0] == ['region', 'total']
            and [(row[0], Decimal(row[1])) for row in output[1:]] == [('east', Decimal(5)), ('west', Decimal('1.25'))]
            and after_query}


def main() -> None:
    """确认CSVkit候选归属并输出本任务真实断言。@return None。"""
    entries = {'CV-U01': (projections, ['quoted_projection_preserves_cells_and_identifiers']),
        'CV-C01': (projections, ['delete_empty_rows_uses_projected_cells_and_pads_short_rows']),
        'CV-U02': (matching, ['match_is_substring_while_file_and_anchored_regex_are_exact', 'multiple_columns_default_to_all_and_any_is_explicit']),
        'CV-U03': (sort_types, ['numeric_and_no_inference_sort_have_different_order']),
        'CV-C02': (sort_types, ['leading_zero_and_blank_policies_preserve_business_text']),
        'CV-C03': (local_sql, ['dialect_only_outputs_schema_without_importing_data']),
        'CV-P01': (local_sql, ['query_without_database_uses_memory_and_outputs_last_result'])}
    observe, fields = entries[sys.argv[1]]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(csvkit.__file__).resolve() == root / 'library/csvkit/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
