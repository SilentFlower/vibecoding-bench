"Public regression tests for DATASET-O02-DEV; the complete business contract is in materials/DATASET-O02-DEV-contract.md."
import dataset
import pytest

def test_find_findone_order_and_named_projection():
    "Verify find findone order and named projection."
    db=dataset.connect('sqlite://');t=db['items'];t.insert_many([{'sku':'a','qty':1,'secret':'x'},{'sku':'b','qty':3,'secret':'y'}])
    rows=list(t.find(_columns=['sku','qty'],order_by='-qty',qty={'>':0}))
    assert list(rows[0])==['sku','qty'] and rows[0]['sku']=='b' and 'secret' not in rows[0]
    assert t.find_one(sku='a',_columns='qty')=={'qty':1}
    db.close()

def test_invalid_empty_duplicate_unknown_and_space_name():
    "Verify invalid empty duplicate unknown and space name."
    db=dataset.connect('sqlite://');t=db['items'];t.insert({'with space':'ok'})
    assert t.find_one(_columns=['with space'])=={'with space':'ok'}
    for columns in [[],['id','id'],['missing']]:
        with pytest.raises(ValueError):list(t.find(_columns=columns))
    db.close()

def test_streamed_custom_row_type_and_no_match():
    "Verify streamed custom row type and no match."
    db=dataset.connect('sqlite://',row_type=lambda items:tuple(items));t=db['items'];t.insert({'x':1,'y':2})
    assert list(t.find(_columns=['y'],_streamed=True))==[(('y',2),)]
    assert t.find_one(x=999,_columns=['y']) is None
    db.close()
