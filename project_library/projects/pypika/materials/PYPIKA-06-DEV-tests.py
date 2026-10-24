"Public regression tests for PYPIKA-06-DEV; the complete business contract is in materials/PYPIKA-06-DEV-contract.md."
import sqlite3
from pypika import Query,Table

def test_compound_null_has_correct_sqlite_truth_table():
    "Verify compound null has correct sqlite truth table."
    table=Table('flags');condition=(table.a==1)|(table.b==2)
    query=Query.from_(table).select(table.id).where(condition.isnull())
    assert '("a"=1 OR "b"=2) IS NULL' in query.get_sql()
    with sqlite3.connect(':memory:') as connection:
        connection.execute('CREATE TABLE flags(id INTEGER,a INTEGER,b INTEGER)')
        connection.executemany('INSERT INTO flags VALUES(?,?,?)',[(1,1,None),(2,0,None),(3,0,2),(4,None,0)])
        assert connection.execute(query.get_sql()).fetchall()==[(2,),(4,)]

def test_notnull_and_outer_combinations_keep_parentheses():
    "Verify notnull and outer combinations keep parentheses."
    table=Table('flags');condition=(table.a==1)&(table.b==2)
    assert condition.isnotnull().get_sql()=='("a"=1 AND "b"=2) IS NOT NULL'
    sql=Query.from_(table).select(table.id).where(condition.isnull()|(table.id==9)).get_sql()
    assert '("a"=1 AND "b"=2) IS NULL OR "id"=9' in sql
    assert table.a.isnull().get_sql()=='a IS NULL'

