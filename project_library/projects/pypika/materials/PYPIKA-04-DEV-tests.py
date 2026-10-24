"Public regression tests for PYPIKA-04-DEV; the complete business contract is in materials/PYPIKA-04-DEV-contract.md."
import sqlite3
from pypika import Query,PostgreSQLQuery,Table

def test_cte_delete_executes_only_selected_rows():
    "Verify cte delete executes only selected rows."
    table=Table('items');selected=Table('selected')
    cte=Query.from_(table).select(table.id).where(table.id<3)
    query=Query.with_(cte,'selected').from_(table).delete().where(table.id.isin(Query.from_(selected).select(selected.id)))
    sql=query.get_sql();assert sql.startswith('WITH selected AS (SELECT')
    with sqlite3.connect(':memory:') as connection:
        connection.execute('CREATE TABLE items(id INTEGER)')
        connection.executemany('INSERT INTO items VALUES(?)',[(1,),(2,),(3,)])
        connection.execute(sql)
        assert connection.execute('SELECT id FROM items').fetchall()==[(3,)]

def test_multiple_ctes_returning_and_plain_delete():
    "Verify multiple ctes returning and plain delete."
    table=Table('items')
    query=PostgreSQLQuery.with_(Query.select(1),'first').with_(Query.select(2),'second').from_(table).delete().where(table.id==1).returning('id')
    sql=query.get_sql()
    assert sql=='WITH first AS (SELECT 1) ,second AS (SELECT 2) DELETE FROM "items" WHERE "id"=1 RETURNING "id"'
    assert Query.from_(table).delete().where(table.id==2).get_sql()=='DELETE FROM "items" WHERE "id"=2'

