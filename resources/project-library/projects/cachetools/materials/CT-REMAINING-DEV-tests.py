"Public regression tests for CT-REMAINING-DEV; the complete business contract is in materials/CT-REMAINING-DEV-contract.md."
from datetime import datetime,timedelta
import pytest
from cachetools import TTLCache

def test_remaining_decreases_and_explicit_time_does_not_change_clock():
    clock=[1];cache=TTLCache(2,5,timer=lambda:clock[0]);cache['a']=1;clock[0]=3
    assert cache.remaining('a')==3 and cache.remaining('a',time=5)==1 and clock[0]==3

def test_boundary_and_missing_keys_raise_without_cleanup():
    clock=[0];cache=TTLCache(2,1,timer=lambda:clock[0]);cache['a']=1;clock[0]=1
    for key in ('a','missing'):
        with pytest.raises(KeyError):
            cache.remaining(key)
    assert 'a' in cache._Cache__data

def test_read_does_not_promote_lru_entry():
    cache=TTLCache(2,10,timer=lambda:0);cache['a']=1;cache['b']=2
    assert cache.remaining('a')==10
    cache['c']=3
    assert 'a' not in cache

def test_datetime_clock_preserves_timedelta_result():
    clock=[datetime(2026,1,1)];cache=TTLCache(2,timedelta(seconds=5),timer=lambda:clock[0]);cache['a']=1
    clock[0]+=timedelta(seconds=2)
    assert cache.remaining('a')==timedelta(seconds=3)
