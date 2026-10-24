"""公开最终查询边界真实执行回归。"""
import sqlite3
import pytest
from sqlglot import parse_one
from sqlglot.report_bounds import bounded_query

def test_existing_inner_limit_and_offset_are_not_overwritten():
    source='SELECT n FROM (SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4) ORDER BY n LIMIT 2 OFFSET 1'
    result=bounded_query(source,10)
    assert sqlite3.connect(':memory:').execute(result.sql(dialect='sqlite')).fetchall()==[(2,),(3,)]

def test_outer_offset_and_zero_limit_apply_to_complete_union():
    source='SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3'
    connection=sqlite3.connect(':memory:')
    assert connection.execute(bounded_query(source,1,offset=1).sql(dialect='sqlite')).fetchall()==[(2,)]
    assert connection.execute(bounded_query(source,0).sql(dialect='sqlite')).fetchall()==[]

def test_original_ast_parent_links_and_cte_are_preserved():
    tree=parse_one('WITH x AS (SELECT 1 AS n) SELECT n FROM x');before=tree.dump()
    result=bounded_query(tree,3)
    assert tree.dump()==before and tree.parent is None and 'WITH x AS' in result.sql()

def test_invalid_bounds_and_dialect_generation_are_explicit():
    for count in (True,-1,1.2):
        with pytest.raises(ValueError): bounded_query('SELECT 1',count)
    assert 'TOP 2' in bounded_query('SELECT 1',2).sql(dialect='tsql')
