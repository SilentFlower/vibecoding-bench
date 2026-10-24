"""公开文档ID分页回归。"""
import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage

def test_pages_and_last_cursor_are_exact():
    with TinyDB(storage=MemoryStorage) as db:
        db.insert_multiple([{'n':i} for i in range(5)])
        rows,cursor=db.query_page(limit=2)
        assert [d.doc_id for d in rows]==[1,2] and cursor==2
        rows,cursor=db.query_page(limit=2,after=cursor)
        assert [d.doc_id for d in rows]==[3,4] and cursor==4
        rows,cursor=db.query_page(limit=2,after=cursor)
        assert [d.doc_id for d in rows]==[5] and cursor is None

def test_sparse_ids_and_filters_do_not_use_offset():
    with TinyDB(storage=MemoryStorage) as db:
        db.insert_multiple([{'n':i} for i in range(6)])
        db.remove(doc_ids=[2,4])
        rows,cursor=db.query_page(Query().n>=2,limit=1,after=1)
        assert [d.doc_id for d in rows]==[3] and cursor==3

def test_return_values_and_predicate_are_detached():
    with TinyDB(storage=MemoryStorage) as db:
        db.insert({'nested':{'value':1}})
        rows,cursor=db.query_page(lambda doc:not doc['nested'].update(value=3))
        rows[0]['nested']['value']=9
        assert db.get(doc_id=1)['nested']['value']==1

def test_invalid_page_arguments_are_rejected():
    with TinyDB(storage=MemoryStorage) as db:
        for options in ({'limit':0},{'limit':True},{'after':-1},{'after':False}):
            with pytest.raises(ValueError):
                db.query_page(**options)
