"""公开真实SQL物理表识别回归。"""
import pytest
from sqlglot import parse_one
from sqlglot.report_inspection import inspect_tables

def test_cte_references_are_not_mistaken_for_physical_tables():
    result=inspect_tables('WITH source AS (SELECT * FROM raw.events) SELECT * FROM source JOIN users u ON source.id=u.id')
    assert [(row.database,row.name) for row in result]==[('raw','events'),('','users')]

def test_self_joins_and_quoted_parts_keep_occurrences():
    result=inspect_tables('SELECT a.id FROM "Catalog"."Schema"."Table" a JOIN "Catalog"."Schema"."Table" b ON a.id=b.id')
    assert [row.alias for row in result]==['a','b'] and all(row.quoted==(True,True,True) for row in result)

def test_nested_scope_and_input_ast_are_preserved():
    tree=parse_one('SELECT * FROM (SELECT * FROM events) e');before=tree.dump()
    assert inspect_tables(tree)[0].name=='events' and tree.dump()==before and tree.parent is None

def test_empty_multistatement_and_mutations_are_rejected():
    for text in ('','SELECT 1;SELECT 2','DELETE FROM events'):
        with pytest.raises(ValueError): inspect_tables(text)
