"Public regression tests for TD-PATH-DEV; the complete business contract is in materials/TD-PATH-DEV-contract.md."
import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage

def test_literal_names_and_nested_paths_have_distinct_results():
    query=Query()
    assert (query.at_path(('a.b','test',''))==3)({'a.b':{'test':{'':3}}})
    assert not (query.at_path(('a','b'))==3)({'a.b':3})

def test_cached_queries_keep_full_path_identity():
    with TinyDB(storage=MemoryStorage) as db:
        db.insert_multiple([{'a':{'x':1},'b':{'x':2}},{'a':{'x':2},'b':{'x':1}}])
        assert [d.doc_id for d in db.search(Query().at_path(('a','x'))==1)]==[1]
        assert [d.doc_id for d in db.search(Query().at_path(('b','x'))==1)]==[2]

def test_subclass_and_original_builder_are_preserved():
    class Custom(Query):
        pass
    base=Custom().outer
    result=base.at_path(iter(['inner']))
    assert isinstance(result,Custom) and base._path==('outer',) and result._path==('outer','inner')

def test_invalid_paths_and_dynamic_map_behavior():
    for value in ('a.b',(),('a',1)):
        with pytest.raises((TypeError,ValueError)):
            Query().at_path(value)
    assert not (Query().map(lambda value:value).at_path(('x',))==1).is_cacheable()
