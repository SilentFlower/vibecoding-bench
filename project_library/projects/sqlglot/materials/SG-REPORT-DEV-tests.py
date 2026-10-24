"Public regression tests for SG-REPORT-DEV; the complete business contract is in materials/SG-REPORT-DEV-contract.md."
import sqlite3
import pytest
from sqlglot import parse_one
from sqlglot.report import prepare_report

def test_composed_query_executes_against_remapped_table_with_values_and_bounds():
    connection=sqlite3.connect(':memory:');connection.execute('create table actual(id integer)');connection.executemany('insert into actual values(?)',[(1,),(2,),(3,)])
    result=prepare_report('SELECT old.id AS value FROM old WHERE old.id>:minimum ORDER BY old.id',values={'minimum':1},tables={('','','old'):('','','actual')},max_rows=1,write='sqlite')
    assert connection.execute(result.sql).fetchall()==[(2,)] and result.output_columns==('value',) and result.parameters==('minimum',)
    assert [table.name for table in result.tables]==['actual']

def test_original_ast_is_preserved_across_reusable_preparations():
    tree=parse_one('SELECT :n AS value');before=tree.dump()
    first=prepare_report(tree,values={'n':1});second=prepare_report(tree,values={'n':2})
    assert first.sql!=second.sql and tree.dump()==before and tree.parent is None

def test_missing_parameters_unused_mapping_and_unbounded_offset_fail():
    with pytest.raises(ValueError): prepare_report('SELECT :missing')
    with pytest.raises(ValueError): prepare_report('SELECT * FROM a',tables={('','','b'):('','','c')})
    with pytest.raises(ValueError): prepare_report('SELECT 1',offset=1)

def test_read_and_write_dialects_are_real_parser_and_generator_options():
    result=prepare_report('SELECT `a` AS `value` FROM `table`',read='mysql',write='postgres',max_rows=2)
    assert '"a"' in result.sql and 'LIMIT 2' in result.sql and result.output_columns==('value',)
