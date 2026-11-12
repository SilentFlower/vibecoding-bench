"Public regression tests for PYPIKA-03-DEV; the complete business contract is in materials/PYPIKA-03-DEV-contract.md."
from pypika import PostgreSQLQuery,Table

def test_empty_update_and_insert_remain_empty_with_suffixes():
    "Verify empty update and insert remain empty with suffixes."
    table=Table('items')
    for query in (PostgreSQLQuery.update(table).returning('*'),
                  PostgreSQLQuery.into(table).on_conflict('id').do_nothing(),
                  PostgreSQLQuery.into(table).on_conflict('id').do_update('name','new').returning('*')):
        assert query.get_sql()=='' and query.get_sql()==''

def test_completing_a_copy_keeps_original_empty():
    "Verify completing a copy keeps original empty."
    table=Table('items');base=PostgreSQLQuery.update(table).returning('*')
    full=base.set('name','new').where(table.id==3)
    assert base.get_sql()=='' and full.get_sql().startswith('UPDATE "items" SET "name"=')
    assert full.get_sql().endswith(' WHERE "id"=3 RETURNING *')
    base=PostgreSQLQuery.into(table).on_conflict('id').do_nothing()
    assert base.get_sql()=='' and base.insert(1).get_sql().endswith(' ON CONFLICT ("id") DO NOTHING')

