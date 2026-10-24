"""公开嵌套配置叶子转换回归。"""
from copy import deepcopy
import pytest
from dpath.transforming import transform_existing

def test_selected_typed_paths_are_transformed_without_mutating_input():
    root={1:{'*':2},'1':{'*':3}}
    result=transform_existing(root,lambda path,value:value*10,predicate=lambda path,value:path[0]==1)
    assert result=={1:{'*':20},'1':{'*':3}} and root=={1:{'*':2},'1':{'*':3}}

def test_new_containers_are_not_visited_again():
    seen=[]
    def transform(path,value):
        seen.append(path)
        return {'new':value}
    result=transform_existing({'a':1},transform)
    assert result=={'a':{'new':1}} and seen==[('a',)]

def test_late_failure_leaves_original_and_callback_values_detached():
    root={'a':bytearray(b'old'),'b':2};before=deepcopy(root)
    def transform(path,value):
        if path==('a',):
            value.extend(b'changed')
            return value
        raise LookupError('synthetic')
    with pytest.raises(LookupError):
        transform_existing(root,transform)
    assert root==before

def test_empty_root_and_empty_nested_containers_can_be_replaced():
    assert transform_existing({},lambda path,value:['root'])==['root']
    assert transform_existing({'a':[]},lambda path,value:'empty')=={'a':'empty'}
