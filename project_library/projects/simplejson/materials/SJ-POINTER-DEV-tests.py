"""公开JSON指针回归。"""
import pytest
from simplejson.pointer import tokens,index,resolve

def test_escaped_keys_empty_keys_and_root_identity():
    value={'a/b':{'~key':[0,{'':4}]}};assert resolve(value,'/a~1b/~0key/1/')==4
    assert resolve(value,'') is value and tokens('/~01')==('~1',)

def test_numeric_mapping_keys_do_not_use_array_rules():
    assert resolve({'01':'value'},'/01')=='value'

def test_invalid_syntax_and_array_indices_fail():
    for pointer in ('abc','#/a','/~2','/~'):
        with pytest.raises(ValueError): tokens(pointer)
    for token in ('01','-1','-','true','+1'):
        with pytest.raises(ValueError): resolve([1,2],'/'+token)

def test_array_bounds_append_index_and_missing_keys():
    assert index('-',2,append=True)==2
    with pytest.raises(IndexError): resolve([1],'/1')
    with pytest.raises(KeyError): resolve({},'/missing')
