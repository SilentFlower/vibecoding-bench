"Public regression tests for PYPIKA-02-DEV; the complete business contract is in materials/PYPIKA-02-DEV-contract.md."
import sqlite3
from pypika import Query,Table
from pypika.terms import ExistsCriterion

def test_select_projection_has_alias_and_executable_result_name():
    "Verify select projection has alias and executable result name."
    inner=Query.select(1).as_('inner_name');expression=ExistsCriterion(inner).as_('has_products')
    sql=Query.select(expression).get_sql()
    assert sql=='SELECT EXISTS (SELECT 1) "has_products"'
    with sqlite3.connect(':memory:') as connection:
        cursor=connection.execute(sql)
        assert cursor.description[0][0]=='has_products' and cursor.fetchone()==(1,)

def test_not_exists_where_has_no_projection_alias():
    "Verify not exists where has no projection alias."
    table=Table('items');inner=Query.from_(table).select(table.id).where(table.id<0)
    expression=ExistsCriterion(inner).negate().as_('absent')
    assert Query.select(expression).get_sql().endswith(' "absent"')
    predicate=Query.select(1).where(expression).get_sql()
    assert 'absent' not in predicate and 'NOT EXISTS' in predicate

