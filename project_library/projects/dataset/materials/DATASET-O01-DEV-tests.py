"Public regression tests for DATASET-O01-DEV; the complete business contract is in materials/DATASET-O01-DEV-contract.md."
import dataset
import pytest
from sqlalchemy import Integer

def test_new_column_override_type_and_partial_row_shapes():
    "Verify new column override type and partial row shapes."
    db=dataset.connect('sqlite://');t=db['items'];t.insert_many([{'key':'a','keep':'old-a'},{'key':'b','keep':'old-b'}])
    t.update_many([{'key':'a','score':3},{'key':'b','keep':'next'}],['key'],types={'score':Integer})
    assert t.find_one(key='a')['score']==3 and t.find_one(key='a')['keep']=='old-a'
    assert t.find_one(key='b')['keep']=='next' and isinstance(t.table.c.score.type,Integer)
    db.close()

def test_missing_keys_checked_before_any_update_or_schema():
    "Verify missing keys checked before any update or schema."
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'key':'a','x':1})
    with pytest.raises(KeyError):t.update_many([{'key':'a','new':2},{'new':3}],['key'],chunk_size=1)
    assert 'new' not in t.columns and t.find_one(key='a')['x']==1
    db.close()

def test_ensure_false_empty_and_bind_name_collision():
    "Verify ensure false empty and bind name collision."
    db=dataset.connect('sqlite://');empty=db['empty'];empty.update_many([],['id']);assert not empty.exists
    t=db['items'];t.insert({'key':'a','_key':1})
    t.update_many([{'key':'a','_key':2,'unknown':9}],['key'],ensure=False)
    assert 'unknown' not in t.columns and t.find_one(key='a')['_key']==2
    db.close()
