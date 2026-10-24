"Public regression tests for AP-WEIGHTED-DEV; the complete business contract is in materials/AP-WEIGHTED-DEV-contract.md."
import pytest
from alive_progress.weighted import alive_weighted_it

def test_actual_work_units_and_item_identity_are_preserved():
    values=[{'n':2},{'n':0},{'n':3}];finished=[]
    result=list(alive_weighted_it(values,lambda value:value['n'],total=5,disable=True,finalize=lambda bar:finished.append(bar.snapshot())))
    assert all(a is b for a,b in zip(result,values)) and finished[0].count==5 and finished[0].processed==5

def test_weight_is_evaluated_once_without_prefetching():
    seen=[]
    def weight(value):
        seen.append(value)
        return value
    iterator=alive_weighted_it(iter([1,2]),weight,disable=True)
    assert next(iterator)==1 and seen==[1]
    iterator.close();assert seen==[1]

def test_invalid_weight_prevents_yield_and_success_finalization():
    for amount in (-1,True,1.5):
        calls=[];iterator=alive_weighted_it([1],lambda value:amount,disable=True,finalize=lambda bar:calls.append(1))
        with pytest.raises(ValueError):
            next(iterator)
        assert calls==[]

def test_empty_source_and_falsey_callable_follow_explicit_presence():
    calls=[]
    class Weight:
        def __bool__(self):
            return False
        def __call__(self,value):
            return 2
    class Ending:
        def __len__(self):
            return 0
        def __call__(self,bar):
            calls.append(bar.snapshot().count)
    assert list(alive_weighted_it([],Weight(),disable=True,finalize=Ending()))==[]
    assert list(alive_weighted_it([1],Weight(),disable=True,finalize=Ending()))==[1] and calls==[0,2]
