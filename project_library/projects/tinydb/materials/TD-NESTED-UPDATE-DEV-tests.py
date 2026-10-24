"Public regression tests for TD-NESTED-UPDATE-DEV; the complete business contract is in materials/TD-NESTED-UPDATE-DEV-contract.md."
import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage
from tinydb.operations import set_path, delete_path

def test_nested_set_preserves_siblings_and_isolates_values():
    data={'items':[]}
    operation=set_path(('a.b','child'),data,create=True)
    data['items'].append('outside')
    first,second={'keep':1},{}
    operation(first);operation(second)
    first['a.b']['child']['items'].append('first')
    assert second['a.b']['child']=={'items':[]} and first['keep']==1

def test_delete_and_missing_policy_are_explicit():
    doc={'a':{'b':1,'c':2}}
    delete_path(('a','b'))(doc)
    assert doc=={'a':{'c':2}}
    delete_path(('missing','x'),missing_ok=True)(doc)

def test_failed_parent_resolution_leaves_document_unchanged():
    doc={'a':3}
    with pytest.raises(TypeError):
        set_path(('a','b'),1,create=True)(doc)
    assert doc=={'a':3}
    with pytest.raises(KeyError):
        set_path(('missing','b'),1)(doc)
    assert doc=={'a':3}

def test_table_update_invalidates_query_cache():
    with TinyDB(storage=MemoryStorage) as db:
        db.insert({'order':{'state':'new'}})
        assert len(db.search(Query().order.state=='new'))==1
        db.update(set_path(('order','state'),'done'))
        assert db.search(Query().order.state=='new')==[] and len(db.search(Query().order.state=='done'))==1
