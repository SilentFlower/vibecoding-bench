"""公开精确配置补丁事务回归。"""
import pytest
from dpath.patches import apply_edits

def test_ordered_array_operations_and_literal_dictionary_keys():
    root={'a/b':[1,3],'*':1}
    result=apply_edits(root,[{'op':'add','path':['a/b',1],'value':2},{'op':'remove','path':['a/b',0]},{'op':'replace','path':['*'],'value':4}])
    assert result=={'a/b':[2,3],'*':4} and root=={'a/b':[1,3],'*':1}

def test_late_failed_test_does_not_commit_partial_work():
    root={'a':1}
    with pytest.raises(ValueError):
        apply_edits(root,[{'op':'replace','path':['a'],'value':2},{'op':'test','path':['a'],'value':3}])
    assert root=={'a':1}

def test_nested_test_types_and_array_indices_are_strict():
    with pytest.raises(ValueError):
        apply_edits({'a':True},[{'op':'test','path':[],'value':{'a':1}}])
    with pytest.raises(TypeError):
        apply_edits([1],[{'op':'remove','path':[True]}])

def test_root_replacement_and_incoming_values_are_detached():
    value={'nested':[]};result=apply_edits(1,[{'op':'replace','path':[],'value':value}])
    result['nested'].append(1)
    assert value=={'nested':[]}
