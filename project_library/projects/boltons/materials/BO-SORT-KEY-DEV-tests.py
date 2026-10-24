"Public regression tests for BO-SORT-KEY-DEV; the complete business contract is in materials/BO-SORT-KEY-DEV-contract.md."
import pytest
from boltons.iterutils import untyped_sorted

def test_key_is_called_once_per_input_occurrence():
    values=[{'v':3},{'v':1},{'v':2}];seen=[]
    result=untyped_sorted(values,key=lambda value:not seen.append(value) and value['v'])
    assert [v['v'] for v in result]==[1,2,3] and seen==values

def test_equal_keys_are_stable_in_both_directions():
    values=[('a',1),('b',1),('c',2)]
    assert untyped_sorted(values,key=lambda value:value[1])==values
    assert untyped_sorted(values,key=lambda value:value[1],reverse=True)==[values[2],values[0],values[1]]

def test_repeated_identity_is_not_memoized_across_occurrences():
    value=object();seen=[]
    assert untyped_sorted([value,value],key=lambda item:not seen.append(item) and 1)==[value,value]
    assert len(seen)==2

def test_invalid_and_raising_keys_are_propagated():
    with pytest.raises(TypeError):
        untyped_sorted([1],key=3)
    def broken(value):
        raise LookupError('synthetic')
    with pytest.raises(LookupError):
        untyped_sorted([1],key=broken)
