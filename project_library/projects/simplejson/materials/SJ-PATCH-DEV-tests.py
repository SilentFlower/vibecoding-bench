"""公开原子JSON补丁回归。"""
import pytest
from simplejson.patch import apply_patch

def test_array_insert_move_and_append_follow_sequential_semantics():
    value={'items':['a','b','c']}
    result=apply_patch(value,[{'op':'move','from':'/items/0','path':'/items/2'},{'op':'add','path':'/items/-','value':'d'}])
    assert result=={'items':['b','c','a','d']} and value=={'items':['a','b','c']}

def test_later_failure_never_changes_original_document():
    value={'v':[1]}
    with pytest.raises(KeyError): apply_patch(value,[{'op':'add','path':'/v/-','value':2},{'op':'remove','path':'/missing'}])
    assert value=={'v':[1]}

def test_test_boolean_and_move_into_child_are_rejected():
    with pytest.raises(ValueError): apply_patch({'v':True},[{'op':'test','path':'/v','value':1}])
    with pytest.raises(ValueError): apply_patch({'a':{'b':{}}},[{'op':'move','from':'/a','path':'/a/b/a'}])

def test_copy_and_root_operations_detach_values():
    original={'a':[1]};result=apply_patch(original,[{'op':'copy','from':'/a','path':'/b'}]);result['b'].append(2)
    assert result['a']==[1] and original=={'a':[1]}
    assert apply_patch(original,[{'op':'remove','path':''}]) is None
