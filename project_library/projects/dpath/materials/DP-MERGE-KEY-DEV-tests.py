"""公开按业务键对齐记录合并回归。"""
import pytest
from dpath.keymerge import merge_by_key

def test_matching_records_merge_and_new_records_append_stably():
    left=[{'id':2,'config':{'a':1,'b':2}},{'id':1,'value':'old'}]
    right=[{'id':1,'value':'new'},{'id':2,'config':{'b':3}},{'id':3,'value':'added'}]
    result=merge_by_key(left,right,'id')
    assert result==[{'id':2,'config':{'a':1,'b':3}},{'id':1,'value':'new'},{'id':3,'value':'added'}]
    assert left[1]['value']=='old' and right[1]['config']=={'b':3}

def test_business_keys_are_type_sensitive():
    result=merge_by_key([{'id':True,'n':1},{'id':1,'n':2}],[{'id':1,'n':3},{'id':'1','n':4}],'id')
    assert [row['n'] for row in result]==[1,3,4]

def test_duplicate_missing_and_unhashable_keys_are_rejected():
    for right in ([{'id':1},{'id':1}],[{}],[{'id':[]} ]):
        with pytest.raises((ValueError,TypeError)):
            merge_by_key([],right,'id')

def test_retained_and_incoming_nested_nodes_are_not_shared():
    left=[{'id':1,'items':[]}];right=[{'id':2,'items':[]}]
    result=merge_by_key(left,right,'id');result[0]['items'].append(1);result[1]['items'].append(2)
    assert left==[{'id':1,'items':[]}] and right==[{'id':2,'items':[]}]
