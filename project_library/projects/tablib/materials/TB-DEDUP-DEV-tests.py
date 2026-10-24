"""公开表格业务去重回归。"""
import pytest
from tablib import Dataset
from tablib.dedup import deduplicate

def test_first_last_and_remove_all_groups_preserve_original_order():
    data=Dataset(['a',1],['b',2],['a',3],['c',4],headers=['id','v'])
    assert list(deduplicate(data,'id'))==[('a',1),('b',2),('c',4)]
    assert list(deduplicate(data,'id',keep='last'))==[('b',2),('a',3),('c',4)]
    assert list(deduplicate(data,'id',keep=False))==[('b',2),('c',4)]

def test_composite_keys_and_type_strictness():
    data=Dataset([True,'x'],[1,'x'],[True,'y'],[True,'x'],headers=['a','b'])
    assert deduplicate(data,['a','b']).height==3

def test_row_tags_and_source_values_remain_independent():
    data=Dataset(headers=['id','value']);data.append(['a',[1]],tags=['active'])
    result=deduplicate(data,'id');result[0][1].append(2)
    assert data[0][1]==[1] and result.filter('active').height==1

def test_empty_headed_data_and_mutable_key_rejection():
    assert deduplicate(Dataset(headers=['id']),'id').height==0
    with pytest.raises(ValueError): deduplicate(Dataset([[1]],headers=['id']),'id')
