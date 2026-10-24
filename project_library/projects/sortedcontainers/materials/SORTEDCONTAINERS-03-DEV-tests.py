"Public regression tests for SORTEDCONTAINERS-03-DEV; the complete business contract is in materials/SORTEDCONTAINERS-03-DEV-contract.md."
import pickle
import unittest
from operator import neg
from sortedcontainers import SortedList,SortedSet,SortedDict

def test_rekeyed_copy_all_container_families_and_identity():
    "Verify rekeyed copy all container families and identity."
    for source in (SortedList([1,3,2]),SortedSet([1,3,2]),SortedDict({1:'a',3:'c',2:'b'})):
        result=source.sorted_copy(key=neg)
        assert list(source)==[1,2,3] and list(result)==[3,2,1]
        assert result.bisect_left(2)==1 and list(result.irange(3,2))==[3,2]
        result._check()
    payload=[];source=SortedDict({1:payload});assert source.sorted_copy(key=neg)[1] is payload

def test_none_strategy_empty_pickle_and_bad_key_preserve_original():
    "Verify none strategy empty pickle and bad key preserve original."
    source=SortedList([1,2,3],key=neg);result=source.sorted_copy()
    assert list(result)==[1,2,3] and list(source)==[3,2,1]
    assert list(pickle.loads(pickle.dumps(result)))==[1,2,3]
    assert list(SortedSet().sorted_copy(key=neg))==[]
    def invalid(value):raise ValueError('key')
    with unittest.TestCase().assertRaises(ValueError):source.sorted_copy(key=invalid)
    assert list(source)==[3,2,1]

