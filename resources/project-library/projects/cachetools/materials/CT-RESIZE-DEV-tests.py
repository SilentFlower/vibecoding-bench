"Public regression tests for CT-RESIZE-DEV; the complete business contract is in materials/CT-RESIZE-DEV-contract.md."
import pytest
from cachetools import LRUCache,FIFOCache,TTLCache

def test_lru_shrink_preserves_original_policy_order():
    cache=LRUCache(4)
    for key in 'abcd':
        cache[key]=key
    cache['a']
    assert cache.resize(2)==(('b','b'),('c','c')) and cache.maxsize==2 and set(cache)=={'a','d'}

def test_weighted_resize_and_growth_are_consistent():
    cache=FIFOCache(8,getsizeof=len);cache['a']='aaa';cache['b']='bb';cache['c']='c'
    assert cache.resize(3)==(('a','aaa'),) and cache.currsize==3
    assert cache.resize(10)==() and cache.maxsize==10

def test_expired_items_do_not_cause_empty_pop_failure():
    clock=[0];cache=TTLCache(2,1,timer=lambda:clock[0]);cache['a']=1;clock[0]=2
    assert cache.resize(0)==() and cache.currsize==0 and cache.maxsize==0
    with pytest.raises(ValueError):
        cache['b']=2

def test_invalid_capacity_leaves_values_and_limit_unchanged():
    cache=LRUCache(2);cache['a']=1
    for size in (-1,float('nan'),True,'2'):
        with pytest.raises(ValueError):
            cache.resize(size)
    assert cache.maxsize==2 and cache['a']==1
