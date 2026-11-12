"""在独立临时SQLite上观察Dataset真实输入、列、事务和查询行为。"""
from __future__ import annotations

from copy import deepcopy
import json
import os
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

import dataset


def inputs(database) -> dict:
    """核列表导入和显式列控制，不使用真实连接配置。@param database 临时库。@return 实际输入事实。"""
    rows = [{'order': 'A', 'qty': 2}, {'order': 'B', 'note': '茶'}]
    before = deepcopy(rows)
    table = database['mixed']
    table.insert_many(rows, chunk_size=1)
    actual = list(table.find(order_by='id'))
    table.insert({'order': 'C', 'unapproved': 'drop-me'}, ensure=False)
    last = table.find_one(order='C')
    stream = database['one_pass']
    consumed = []

    def source():
        """提供明确非Sequence的一次生成器。@return 两条合成记录。"""
        for row in [{'order': 'A'}, {'order': 'B'}]:
            consumed.append(row['order'])
            yield row

    stream.insert_many(source())
    return {'heterogeneous_columns_union': {'order', 'qty', 'note'}.issubset(table.columns)
            and [(row['order'], row['qty'], row['note']) for row in actual] == [('A', 2, None), ('B', None, '茶')],
        'input_dictionaries_unchanged': rows == before,
        'ensure_false_filters_unknown_fields': last['order'] == 'C' and 'unapproved' not in table.columns and 'unapproved' not in last,
        'one_shot_input_is_consumed_by_prescan': consumed == ['A', 'B'] and stream.count() == 0}


def transactions(database) -> dict:
    """在预建表上对照异常边界，避免把DDL误当事务承诺。@param database 临时库。@return 事务事实。"""
    table = database['transactions']
    table.insert({'order': 'seed', 'qty': 0})
    table.delete(order='seed')
    try:
        with database:
            table.insert({'order': 'outside', 'qty': 1}, ensure=False)
            raise ValueError('synthetic validation failure')
    except ValueError:
        pass
    outside = table.count(order='outside')
    with database:
        try:
            table.insert({'order': 'inside', 'qty': 1}, ensure=False)
            raise ValueError('synthetic validation failure')
        except ValueError:
            pass
    inside = table.count(order='inside')
    return {'escaping_context_error_rolls_back': outside == 0,
        'caught_inside_context_commits': inside == 1}


def identities(database) -> dict:
    """核upsert实际匹配行与SQLite普通索引，不推测并发结果。@param database 临时库。@return 业务身份事实。"""
    table = database['identities']
    table.insert_many([{'order': 'A', 'qty': 1}, {'order': 'A', 'qty': 2}])
    result = table.upsert({'order': 'A', 'qty': 9}, ['order'])
    rows = list(table.find(order='A', order_by='id'))
    indexes = list(database.query('PRAGMA index_list("identities")'))
    return {'upsert_updates_all_existing_key_matches': result is True and len(rows) == 2 and [row['qty'] for row in rows] == [9, 9],
        'automatic_key_index_is_not_unique': bool(indexes) and all(row['unique'] == 0 for row in indexes)}


def queries(database) -> dict:
    """核明确排序和字面参数绑定。@param database 临时库。@return 查询事实。"""
    table = database['reports']
    literal = "x' OR 1=1 --"
    table.insert_many([{'order': 'A', 'score': 10, 'status': literal},
        {'order': 'B', 'score': 10, 'status': 'ready'}, {'order': 'C', 'score': 5, 'status': 'ready'}])
    ordered = list(table.find(order_by=['score', 'id'], _limit=2, _offset=1))
    bound = list(database.query('SELECT "order" FROM reports WHERE status = :status ORDER BY id', status=literal))
    return {'explicit_order_limit_offset_are_repeatable': [row['order'] for row in ordered] == ['A', 'B'],
        'named_bind_preserves_literal_value': [row['order'] for row in bound] == ['A']}


def main() -> None:
    """显式临时SQLite连接，输出当前任务真实事实后关闭。@return None。"""
    task = sys.argv[1]
    fields = {'DS-U01': ('heterogeneous_columns_union', 'input_dictionaries_unchanged'),
        'DS-C01': ('ensure_false_filters_unknown_fields',),
        'DS-U02': ('escaping_context_error_rolls_back', 'caught_inside_context_commits'),
        'DS-P01': ('escaping_context_error_rolls_back', 'ensure_false_filters_unknown_fields'),
        'DS-U03': ('upsert_updates_all_existing_key_matches',),
        'DS-C02': ('upsert_updates_all_existing_key_matches', 'automatic_key_index_is_not_unique'),
        'DS-U04': ('explicit_order_limit_offset_are_repeatable', 'named_bind_preserves_literal_value')}
    with TemporaryDirectory(prefix='dataset-synthetic-') as directory:
        database = dataset.connect('sqlite:///' + str(Path(directory) / 'orders.sqlite'))
        try:
            if task in ('DS-U01', 'DS-C01'):
                facts = inputs(database)
            elif task in ('DS-U02', 'DS-P01'):
                facts = transactions(database)
                if task == 'DS-P01':
                    facts.update(inputs(database))
            elif task in ('DS-U03', 'DS-C02'):
                facts = identities(database)
            else:
                facts = queries(database)
        finally:
            database.close()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(dataset.__file__).resolve() == root / 'library/dataset/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
