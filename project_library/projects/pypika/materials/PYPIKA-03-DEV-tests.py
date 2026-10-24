"""未完成PG语句不生成孤立RETURNING或冲突后缀。"""
from pypika import PostgreSQLQuery,Table

def test_empty_update_and_insert_remain_empty_with_suffixes():
    """所有后缀组合服从基础空串契约。@return None。"""
    table=Table('items')
    for query in (PostgreSQLQuery.update(table).returning('*'),
                  PostgreSQLQuery.into(table).on_conflict('id').do_nothing(),
                  PostgreSQLQuery.into(table).on_conflict('id').do_update('name','new').returning('*')):
        assert query.get_sql()=='' and query.get_sql()==''

def test_completing_a_copy_keeps_original_empty():
    """补齐真实赋值或插入后才输出完整SQL。@return None。"""
    table=Table('items');base=PostgreSQLQuery.update(table).returning('*')
    full=base.set('name','new').where(table.id==3)
    assert base.get_sql()=='' and full.get_sql().startswith('UPDATE "items" SET "name"=')
    assert full.get_sql().endswith(' WHERE "id"=3 RETURNING *')
    base=PostgreSQLQuery.into(table).on_conflict('id').do_nothing()
    assert base.get_sql()=='' and base.insert(1).get_sql().endswith(' ON CONFLICT ("id") DO NOTHING')

