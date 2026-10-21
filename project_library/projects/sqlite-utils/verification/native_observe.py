"""隔离执行 SQLite 真实业务，使用独立 SQL 值核候选而非候选自报。"""
from __future__ import annotations

import argparse
from functools import partial
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Callable

from sqlite_utils import Database
import sqlite_utils


def observe(operation: Callable[[], object]) -> object:
    """保存每项真实异常。@param operation 业务操作。@return 值或异常类型。"""
    try:
        return operation()
    except Exception as error:
        return {'error_type': type(error).__name__}


def cli(arguments: list[str], data: str = '') -> subprocess.CompletedProcess:
    """用候选模块执行真实 CLI。@param arguments 参数。@param data 合成输入。@return 进程结果。"""
    return subprocess.run([sys.executable, '-I', '-B', '-m', 'sqlite_utils', *arguments],
        input=data, capture_output=True, text=True, timeout=10)


def persistence() -> dict:
    """核 CLI、Python 连接和独立标准库读取同一真实文件。@return 行与内存反例。"""
    with TemporaryDirectory(prefix='sq-orders-') as directory:
        path = Path(directory) / 'orders.db'
        process = cli(['insert', str(path), 'orders', '-', '--csv', '--pk', 'id'],
            'id,qty\nA,1\nB,2\n')
        with sqlite3.connect(path) as connection:
            rows = connection.execute('select id,qty from orders order by id').fetchall()
        fresh = subprocess.run([sys.executable, '-I', '-B', '-c',
            'import json,sys;from sqlite_utils import Database;d=Database(sys.argv[1]);'
            'print(json.dumps(list(d["orders"].rows)));d.close()', str(path)],
            capture_output=True, text=True, timeout=10)
        memory = Database(memory=True)
        memory['orders'].insert({'id': 'A'})
        memory.close()
        reopened = Database(memory=True)
        empty = not reopened['orders'].exists()
        reopened.close()
        return {'file_cli_python_sqlite': process.returncode == fresh.returncode == 0
            and rows == [('A', 1), ('B', 2)] and json.loads(fresh.stdout) == [
                {'id': 'A', 'qty': 1}, {'id': 'B', 'qty': 2}], 'memory_does_not_persist': empty}


def upsert_plan() -> dict:
    """真实见证保留省略列的重复导入及错误替代方案。@return 可行性和反例。"""
    db = Database(memory=True)
    table = db['orders'].create({'id': str, 'qty': int, 'memo': str}, pk='id')
    table.insert({'id': '001', 'qty': 1, 'memo': 'keep'})
    batch = [{'id': '001', 'qty': 5}, {'id': '002', 'qty': 2}]
    table.upsert_all(batch, pk='id')
    table.upsert_all(batch, pk='id')
    good = list(table.rows_where(order_by='id')) == [
        {'id': '001', 'qty': 5, 'memo': 'keep'}, {'id': '002', 'qty': 2, 'memo': None}]
    duplicate = db['duplicates'].insert_all(batch).insert_all(batch).count == 4
    table.insert({'id': '001', 'qty': 7}, replace=True)
    replacement_loses_memo = table.get('001')['memo'] is None
    db.close()
    return {'upsert_preserves_omitted': good, 'plain_insert_duplicates': duplicate,
        'replace_loses_memo': replacement_loses_memo}


def inference() -> dict:
    """核首批推断与 SQLite 亲和性，并保留普通文本对照。@return 实际类型和值。"""
    db = Database(memory=True)
    records = [{'id': index, 'code': index} for index in range(200)] + [{'id': 200, 'code': '007'}]
    table = db['inferred'].insert_all(iter(records), pk='id')
    inferred = db.execute('select code,typeof(code) from inferred where id=200').fetchone()
    text = db['explicit'].insert_all(iter(records), pk='id', columns={'code': str})
    declared = db.execute('select code,typeof(code) from explicit where id=200').fetchone()
    table.insert({'id': 201, 'code': 'ordinary'})
    normal = table.get(201)['code'] == 'ordinary'
    existing = db['existing'].create({'id': int, 'code': str}, pk='id').insert_all(iter(records))
    result = {'inferred_integer_loses_zeros': tuple(inferred) == (7, 'integer'),
        'prospective_text_preserves': tuple(declared) == ('007', 'text'),
        'ordinary_text_preserved': normal, 'existing_text_preserved': existing.get(200)['code'] == '007'}
    db.close()
    return result


def null_example() -> dict:
    """抽取唯一示例并检查真实文件，不以打印预期字符串代替导入。@return 原生验证结果。"""
    answer = Path(os.environ['PROJECT_ANSWER_FILE']).read_text(encoding='utf-8')
    blocks = re.findall(r'```(?:python|py)\s*\n(.*?)```', answer, re.S | re.I)
    if len(blocks) != 1:
        return {'unique_python_block': False, 'default_empty_string': False,
            'example_creates_actual_nulls': False}
    with TemporaryDirectory(prefix='sq-example-') as directory:
        root = Path(directory)
        csv_data = 'id,note,qty\n1,,0\n2, ,3\n3,北方,2\n'
        data = root / 'orders.csv'
        data.write_text(csv_data, encoding='utf-8')
        default = root / 'default.db'
        control = cli(['insert', str(default), 'orders', str(data), '--csv'])
        with sqlite3.connect(default) as connection:
            plain = connection.execute('select note,typeof(note) from orders where id=1').fetchone()
        script = root / 'example.py'
        script.write_text(blocks[0], encoding='utf-8')
        path = root / 'candidate.db'
        process = subprocess.run([sys.executable, '-I', '-B', str(script), str(path), str(data)],
            capture_output=True, text=True, timeout=12)
        actual = []
        if path.is_file():
            with sqlite3.connect(path) as connection:
                actual = connection.execute('select id,note,typeof(note),qty,typeof(qty) from orders order by id').fetchall()
        return {'unique_python_block': True,
            'default_empty_string': control.returncode == 0 and plain == ('', 'text'),
            'example_creates_actual_nulls': process.returncode == 0 and actual == [
                (1, None, 'null', 0, 'integer'), (2, ' ', 'text', 3, 'integer'),
                (3, '北方', 'text', 2, 'integer')]}


def search_ids(table, query: str) -> list[int]:
    """取真实 MATCH 业务主键。@param table 内容表。@param query 查询。@return 排序主键。"""
    return sorted(row['id'] for row in table.search(query))


def fts_case(version: str, triggers: bool, form: str, empty: bool = False,
             quoted: bool = False, token: bool = False) -> bool:
    """核一次性列配置及兼容矩阵。@param version FTS版本。@param triggers 触发器。

    @param form 输入形式。@param empty 空表。@param quoted 含空格标识符。@param token 分词器。
    @return SQL实际命中及数据保真是否通过。
    """
    db = Database(memory=True)
    name, field = ('work notes', 'body text') if quoted else ('notes', 'body')
    table = db[name].create({'id': int, field: str, 'extra': str}, pk='id')
    if not empty:
        table.insert({'id': 1, field: 'running azure', 'extra': 'keep'})
        table.insert({'id': 2, field: 'gold', 'extra': 'azure hidden'})
    before = list(table.rows_where(order_by='id'))
    columns = [field]
    supplied = {'list': lambda: columns, 'tuple': lambda: tuple(columns),
        'iterator': lambda: iter(columns), 'generator': lambda: (value for value in columns)}[form]()
    result = table.enable_fts(supplied, fts_version=version, create_triggers=triggers,
        tokenize='porter' if token else None)
    good = result is table and list(table.rows_where(order_by='id')) == before
    good = good and search_ids(table, 'azure') == ([] if empty else [1])
    if token and not empty:
        good = good and search_ids(table, 'run') == [1]
    table.insert({'id': 3, field: 'violet', 'extra': 'keep later'})
    good = good and search_ids(table, 'violet') == ([3] if triggers else [])
    if version == 'FTS5' and triggers:
        table.update(3, {field: 'silver'})
        good = good and search_ids(table, 'violet') == [] and search_ids(table, 'silver') == [3]
        table.delete(3)
        good = good and search_ids(table, 'silver') == []
    if not triggers:
        table.rebuild_fts()
        good = good and search_ids(table, 'violet') == [3]
    db.close()
    return good


def fts_replace() -> bool:
    """核相同配置不发DDL、不同配置重新索引。@return 行为是否保持。"""
    db = Database(memory=True)
    table = db['notes'].insert({'id': 1, 'body': 'azure', 'other': 'violet'}, pk='id')
    table.enable_fts(['body'], create_triggers=True)
    trace = []
    db.conn.set_trace_callback(trace.append)
    table.enable_fts(iter(['body']), create_triggers=True, replace=True)
    no_ddl = not any(sql.lstrip().upper().startswith(('CREATE', 'DROP', 'ALTER', 'INSERT', 'UPDATE', 'DELETE')) for sql in trace)
    db.conn.set_trace_callback(None)
    table.enable_fts((value for value in ['other']), create_triggers=False, replace=True)
    changed = search_ids(table, 'azure') == [] and search_ids(table, 'violet') == [1]
    db.close()
    return no_ddl and changed


def fts_observations() -> dict:
    """执行有限迭代、FTS4初始化插入及FTS5完整CRUD。@return 分项事实。"""
    cases = {}
    for version in ('FTS4', 'FTS5'):
        for triggers in (False, True):
            for form in ('list', 'tuple', 'iterator', 'generator'):
                key = f'{version}_{"triggers" if triggers else "manual"}_{form}'
                cases[key] = observe(lambda v=version, t=triggers, f=form: fts_case(v, t, f))
    cases['empty_table'] = observe(lambda: fts_case('FTS5', True, 'iterator', empty=True))
    cases['quoted_tokenize'] = observe(lambda: fts_case('FTS5', True, 'generator', quoted=True, token=True))
    cases['replace_semantics'] = observe(fts_replace)
    return cases


def fts_lifecycle() -> dict:
    """核已存在API及一次性输入故障，明确不承诺FTS4 UPDATE。@return 原版事实。"""
    db = Database(memory=True)
    table = db['notes'].insert({'id': 1, 'body': 'azure', 'extra': 'violet'}, pk='id')
    original = list(table.rows)
    table.enable_fts(['body'], fts_version='FTS5')
    initial = list(table.rows) == original and search_ids(table, 'azure') == [1] and search_ids(table, 'violet') == []
    table.insert({'id': 2, 'body': 'violet', 'extra': 'keep'})
    stale = search_ids(table, 'violet') == []
    table.rebuild_fts()
    rebuilt = search_ids(table, 'violet') == [2]
    db.close()
    return {'content_preserved_and_selected_columns': initial, 'default_later_insert_stale': stale,
        'rebuild_restores_search': rebuilt, 'FTS5_trigger_crud': observe(lambda: fts_case('FTS5', True, 'list'))}


def fts_diagnosis() -> dict:
    """核公开的一次性输入失败证据。@return 列表对照和实际遗留表。"""
    db = Database(memory=True)
    table = db['notes'].insert({'id': 1, 'body': 'azure'}, pk='id')
    failed = False
    try:
        table.enable_fts(iter(['body']), create_triggers=True)
    except sqlite3.OperationalError as error:
        failed = 'syntax error' in str(error)
    leftover = db['notes_fts'].exists()
    db.close()
    return {'list_control_succeeds': fts_case('FTS5', True, 'list'),
        'one_shot_syntax_error': failed, 'partial_fts_table_remains': leftover}


def convert_case(form: str, across_tables: bool = False) -> bool:
    """用不同映射验证每次回调被实际调用。@param form callable形式。@param across_tables 跨表。

    @return 当前两列实际值是否正确。
    """
    db = Database(memory=True)
    table = db['places'].insert({'id': 1, 'state': 'CA', 'country': 'US'}, pk='id')
    target = db['other'].insert({'id': 1, 'country': 'US'}, pk='id') if across_tables else table
    first, second = {'CA': 'California'}, {'US': 'United States'}
    if form == 'bound':
        left, right = first.get, second.get
    elif form == 'partial':
        left, right = partial(first.get), partial(second.get)
    elif form == 'object':
        class Mapper:
            """模拟无__name__的同步映射对象。"""
            def __init__(self, values: dict) -> None:
                """保存当前映射。@param values 数据。@return None。"""
                self.values = values

            def __call__(self, value):
                """使用对象自身的映射。@param value 输入。@return 映射结果。"""
                return self.values.get(value)

        left, right = Mapper(first), Mapper(second)
    elif form == 'same_name':
        def factory(mapping):
            """创建不同闭包、相同名字。@param mapping 映射。@return callable。"""
            def normalize(value):
                """查当前闭包。@param value 输入。@return 对应值。"""
                return mapping.get(value)
            return normalize
        left, right = factory(first), factory(second)
    else:
        left, right = lambda value: first.get(value), lambda value: second.get(value)
    table.convert('state', left)
    target.convert('country', right)
    good = table.get(1)['state'] == 'California' and target.get(1)['country'] == 'United States'
    db.close()
    return good


def convert_compatibility() -> dict:
    """保护公开注册、where/output/Falsey/multi及异常事务。@return 逐项事实。"""
    db = Database(memory=True)
    table = db['values'].insert_all([{'id': 1, 'raw': 'ca'}, {'id': 2, 'raw': 'ny'}], pk='id')
    table.convert('raw', str.upper, output='normalized', where='id = :id', where_args={'id': 1})
    selective = list(table.rows_where(order_by='id')) == [
        {'id': 1, 'raw': 'ca', 'normalized': 'CA'}, {'id': 2, 'raw': 'ny', 'normalized': None}]
    # 显式无文本亲和性的列隔离转换行为，避免混合输入推断为TEXT先把0变为字符串。
    falsey = db['falsey'].create({'id': int, 'v': bytes}, pk='id').insert_all([
        {'id': 1, 'v': 0}, {'id': 2, 'v': ''}, {'id': 3, 'v': False}])
    seen = []
    def record(value):
        """记录零和空串没有被跳过。@param value 输入。@return 非空标记。"""
        seen.append(value)
        return f'got:{value}'
    falsey.convert('v', record)
    falsey_ok = seen == [0, '', 0] and [row['v'] for row in falsey.rows_where(order_by='id')] == ['got:0', 'got:', 'got:0']
    repeat = db['repeat'].insert({'id': 1, 'v': 'a'}, pk='id')
    def suffix(value):
        """重复调用同对象仍执行当前值。@param value 输入。@return 新值。"""
        return value + '!'
    repeat.convert('v', suffix).convert('v', suffix)
    same_callback = repeat.get(1)['v'] == 'a!!'
    multi = db['multi'].insert({'id': 1, 'v': 'a'}, pk='id')
    multi.convert('v', lambda value: {'new': value.upper()}, multi=True)
    multi_ok = multi.get(1) == {'id': 1, 'v': 'a', 'new': 'A'}
    data = db['errors'].insert_all([{'id': 1, 'v': 1}, {'id': 2, 'v': 2}], pk='id')
    def fail_second(value):
        """故意让第二行失败以核原UPDATE事务。@param value 输入。@return 值或错误。"""
        if value == 2:
            raise ValueError('synthetic callback error')
        return 90
    failed = False
    try:
        data.convert('v', fail_second)
    except sqlite3.OperationalError:
        failed = True
    rollback = failed and [row['v'] for row in data.rows_where(order_by='id')] == [1, 2]
    db.register_function(lambda value: 'old', name='public_fn')
    db.register_function(lambda value: 'new', name='public_fn')
    default = db.execute("select public_fn('x')").fetchone()[0] == 'old'
    db.register_function(lambda value: 'new', name='public_fn', replace=True)
    explicit = db.execute("select public_fn('x')").fetchone()[0] == 'new'
    db.close()
    return {'output_where_preserves_raw': selective, 'falsey_values_called': falsey_ok,
        'same_callback_repeated': same_callback, 'multi_preserved': multi_ok,
        'callback_error_rolls_back_update': rollback, 'public_default_preserved': default,
        'public_explicit_replace': explicit}


def convert_observations() -> dict:
    """核四种冲突callable、lambda及共享连接。@return 真实结果。"""
    return {**{f'{form}_{"cross_table" if cross else "same_table"}': observe(
        lambda f=form, c=cross: convert_case(f, c))
        for form in ('bound', 'partial', 'object', 'same_name', 'lambda') for cross in (False, True)},
        **convert_compatibility()}


def main() -> None:
    """选择冻结观察入口。@return None，标准输出只有JSON。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['persistence', 'upsert', 'inference', 'null-example',
        'fts-lifecycle', 'fts-diagnosis', 'fts', 'convert', 'normalization', 'convert-diagnosis'])
    args = parser.parse_args()
    modes = {'persistence': persistence, 'upsert': upsert_plan, 'inference': inference,
        'null-example': null_example, 'fts-lifecycle': fts_lifecycle, 'fts-diagnosis': fts_diagnosis,
        'fts': fts_observations,
        'convert': convert_observations, 'normalization': convert_compatibility,
        'convert-diagnosis': lambda: {'original_bound_collision': not convert_case('bound'),
            'lambda_control': convert_case('lambda')}}
    expected_root = Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')) / 'library'
    result = {'candidate_import': Path(sqlite_utils.__file__).resolve().is_relative_to(expected_root.resolve()),
        **modes[args.mode]()}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
