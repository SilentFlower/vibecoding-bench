"""公开表映射真实SQL回归。"""
import sqlite3
import pytest
from sqlglot import parse_one
from sqlglot.report_remap import remap_tables
from sqlglot.report_inspection import inspect_tables

def test_generated_query_executes_with_preserved_original_qualifier():
    connection=sqlite3.connect(':memory:');connection.execute('create table new_table(id integer)');connection.execute('insert into new_table values(7)')
    result=remap_tables('SELECT old_table.id FROM old_table',{('','','old_table'):('','','new_table')})
    assert connection.execute(result.sql(dialect='sqlite')).fetchall()==[(7,)]

def test_cte_shadowing_and_existing_alias_are_kept():
    query='WITH local AS (SELECT id FROM base) SELECT x.id FROM local x JOIN target t ON x.id=t.id'
    result=remap_tables(query,{('','','base'):('','archive','base_new'),('','','target'):('','','target_new')})
    assert {row.name for row in inspect_tables(result)}=={'base_new','target_new'} and 'local AS' in result.sql() and 'AS t' in result.sql()

def test_replacement_names_are_quoted_as_data_and_ast_is_unchanged():
    source=parse_one('SELECT old.id FROM old');before=source.dump();result=remap_tables(source,{('','','old'):('','','strange;name')})
    assert inspect_tables(result)[0].name=='strange;name' and source.dump()==before

def test_unused_keys_and_malformed_names_fail_clearly():
    with pytest.raises(ValueError): remap_tables('SELECT * FROM a',{('','','b'):('','','c')},require_all=True)
    with pytest.raises(ValueError): remap_tables('SELECT * FROM a',{('','','a'):('catalog','','name')})
