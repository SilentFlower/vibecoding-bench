"""公开真实表格关联回归。"""
import pytest
from tablib import Dataset
from tablib.joining import join

def test_many_to_many_order_and_nonkey_suffixes():
    left=Dataset([1,'a'],[1,'b'],headers=['id','name']);right=Dataset([1,'x'],[1,'y'],headers=['id','name'])
    result=join(left,right,'id',how='inner')
    assert result.headers==['id','name_left','name_right'] and list(result)==[(1,'a','x'),(1,'a','y'),(1,'b','x'),(1,'b','y')]

def test_outer_unmatched_right_keys_are_not_lost():
    left=Dataset([1,'a'],headers=['id','left']);right=Dataset([2,'b'],headers=['id','right'])
    assert list(join(left,right,'id',how='outer'))==[(1,'a',None),(2,None,'b')]

def test_null_keys_and_bool_number_keys_have_explicit_semantics():
    left=Dataset([None],[True],headers=['id']);right=Dataset([None],[1],headers=['id'])
    assert join(left,right,'id',how='inner').height==0
    assert list(join(left,right,'id',how='inner',nulls='equal'))==[(None,)]

def test_budget_and_name_collisions_fail_without_input_mutation():
    left=Dataset([1],[1],headers=['id']);right=Dataset([1],[1],headers=['id'])
    with pytest.raises(ValueError): join(left,right,'id',max_rows=3)
    assert left.height==right.height==2
    with pytest.raises(ValueError): join(Dataset([1,2,3],headers=['id','x','x_left']),Dataset([1,2],headers=['id','x']),'id')
