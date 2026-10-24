"""公开命名空间压缩冲突回归。"""
import pytest
import xmltodict

def test_distinct_expanded_elements_cannot_silently_merge_in_error_mode():
    text='<r xmlns:a="urn:a" xmlns:b="urn:b"><a:x>1</a:x><b:x>2</b:x></r>'
    options={'process_namespaces':True,'namespaces':{'urn:a':None,'urn:b':None}}
    assert xmltodict.parse(text,**options)['r']['x']==['1','2']
    with pytest.raises(ValueError):
        xmltodict.parse(text,namespace_collision='error',**options)

def test_attribute_collision_is_rejected_before_overwriting():
    text='<r xmlns:a="urn:a" xmlns:b="urn:b" a:x="1" b:x="2"/>'
    with pytest.raises(ValueError):
        xmltodict.parse(text,process_namespaces=True,namespaces={'urn:a':None,'urn:b':None},namespace_collision='error')

def test_same_name_repeats_and_distinct_parents_are_valid():
    text='<r xmlns:a="urn:a" xmlns:b="urn:b"><one><a:x>1</a:x><a:x>2</a:x></one><two><b:x>3</b:x></two></r>'
    result=xmltodict.parse(text,process_namespaces=True,namespaces={'urn:a':None,'urn:b':None},namespace_collision='error')
    assert result['r']['one']['x']==['1','2'] and result['r']['two']['x']=='3'

def test_invalid_policy_is_rejected_before_input_use():
    with pytest.raises(ValueError):
        xmltodict.parse('<r/>',namespace_collision='ignore')
