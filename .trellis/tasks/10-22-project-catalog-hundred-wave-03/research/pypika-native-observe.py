"""以本地合成SQLite数据核查询条件、绑定参数及构造器状态。"""
from json import dumps
from os import environ
from pathlib import Path
from sqlite3 import Connection, connect
from sys import argv

import pypika
from pypika import MySQLQuery, PostgreSQLQuery, Query, Table
from pypika.queries import QueryBuilder
from pypika.terms import NamedParameter


def database() -> Connection:
    """创建仅属于本进程的合成商品表。@return 独立内存数据库。"""
    result = connect(':memory:')
    result.execute('CREATE TABLE items(id INTEGER, name TEXT, active INTEGER, price INTEGER, deleted_at TEXT)')
    result.executemany('INSERT INTO items VALUES(?,?,?,?,?)', [
        (1, 'Tea', 0, 20, None), (2, 'Book', 1, 20, '2026-10-20'),
        (3, 'Pen', 1, 5, None), (4, "O'Reilly", 1, 30, None)])
    return result


def ids(connection: Connection, query: QueryBuilder) -> list[int]:
    """执行真实生成SQL，避免只比对字符串自报成功。@param connection 合成库。@param query 查询。@return 商品ID。"""
    return [row[0] for row in connection.execute(query.get_sql()).fetchall()]


def main() -> None:
    """在真实候选源码上运行单项冻结业务，始终关闭内存数据库。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(pypika.__file__).resolve() == root / 'library/pypika/__init__.py'}
    table = Table('items')
    connection = database()
    try:
        base = Query.from_(table).select(table.id)
        if argv[1] == 'PQ-U01':
            # Python的and会先求对象真值；位运算符才组合真实SQL条件。
            wrong = base.where((table.active == 1) and (table.price > 10))
            correct = base.where((table.active == 1) & (table.price > 10))
            result['python_boolean_and_drops_a_sql_predicate'] = (
                ids(connection, wrong) == [1, 2, 4] and ids(connection, correct) == [2, 4])
        elif argv[1] == 'PQ-U02':
            result['sql_null_requires_null_predicate_instead_of_equality'] = (
                ids(connection, base.where(table.deleted_at == None)) == []
                and ids(connection, base.where(table.deleted_at.isnull())) == [1, 3, 4])
        elif argv[1] == 'PQ-C01':
            parameter = NamedParameter()
            sql = base.where(table.name == "O'Reilly").get_sql(parameter=parameter)
            rows = connection.execute(sql, parameter.get_parameters()).fetchall()
            adversarial = NamedParameter()
            other = base.where(table.name == "x' OR 1=1 --").get_sql(parameter=adversarial)
            result['named_values_are_bound_separately_from_query_text'] = (
                rows == [(4,)] and parameter.get_parameters() == {'param1': "O'Reilly"}
                and "O'Reilly" not in sql
                and connection.execute(other, adversarial.get_parameters()).fetchall() == [])
        elif argv[1] == 'PQ-C02':
            reserved = Table('order')
            column = reserved.field('select')
            mysql = MySQLQuery.from_(reserved).select(column).get_sql()
            postgres = PostgreSQLQuery.from_(reserved).select(column).get_sql()
            result['identifier_lookup_and_dialect_quoting_are_explicit_controls'] = (
                callable(reserved.select) and reserved['select'].name == column.name == 'select'
                and mysql == 'SELECT `select` FROM `order`'
                and postgres == 'SELECT "select" FROM "order"')
        elif argv[1] == 'PQ-P01':
            parameter = NamedParameter()
            first = base.where(table.name == "O'Reilly").get_sql(parameter=parameter)
            live = parameter.get_parameters()
            snapshot = dict(live)
            second = base.where(table.name == 'Tea').get_sql(parameter=parameter)
            result['parameter_collectors_accumulate_and_require_snapshot_ownership'] = (
                live is parameter.get_parameters() and live == {'param1': "O'Reilly", 'param2': 'Tea'}
                and snapshot == {'param1': "O'Reilly"}
                and connection.execute(first, snapshot).fetchall() == [(4,)]
                and connection.execute(second, parameter.get_parameters()).fetchall() == [(1,)])
        elif argv[1] == 'PQ-D01':
            base.where(table.active == 1)
            corrected = base.where(table.active == 1)
            result.update(discarded_return_ids=ids(connection, base), captured_return_ids=ids(connection, corrected),
                original_sql=base.get_sql(), captured_sql=corrected.get_sql(), original_is_captured=base is corrected)
        else:
            raise ValueError('未冻结的业务任务')
    finally:
        connection.close()
    print(dumps(result))


if __name__ == '__main__':
    main()
