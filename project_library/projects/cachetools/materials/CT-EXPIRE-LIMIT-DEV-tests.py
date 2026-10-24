"Public regression tests for CT-EXPIRE-LIMIT-DEV; the complete business contract is in materials/CT-EXPIRE-LIMIT-DEV-contract.md."
import pytest
from cachetools import TTLCache

def test_repeated_bounded_expiry_preserves_order_and_finishes():
    clock=[0];cache=TTLCache(5,1,timer=lambda:clock[0]);cache.update(a=1,b=2,c=3);clock[0]=2
    assert cache.expire(limit=1)==[('a',1)]
    assert cache.expire(limit=1)==[('b',2)]
    assert cache.expire(limit=1)==[('c',3)] and cache.expire(limit=1)==[]

def test_zero_limit_and_live_entries_are_preserved():
    clock=[0];cache=TTLCache(5,2,timer=lambda:clock[0]);cache['old']=1;clock[0]=1;cache['live']=2;clock[0]=2
    assert cache.expire(limit=0)==[] and 'old' in cache._Cache__data
    assert cache.expire(limit=1)==[('old',1)] and cache['live']==2

def test_weighted_sizes_are_correct_after_partial_cleanup():
    clock=[0];cache=TTLCache(8,1,timer=lambda:clock[0],getsizeof=len);cache['a']='aaa';cache['b']='bb';clock[0]=2
    assert cache.expire(limit=1)==[('a','aaa')] and cache._Cache__currsize==2
    assert cache.expire()==[('b','bb')] and cache.currsize==0

def test_invalid_limit_fails_before_timer_read():
    clock=[0];cache=TTLCache(2,1,timer=lambda:clock[0]);cache['a']=1
    for value in (-1,True,1.5):
        with pytest.raises(ValueError):
            cache.expire(limit=value)
    assert cache['a']==1
