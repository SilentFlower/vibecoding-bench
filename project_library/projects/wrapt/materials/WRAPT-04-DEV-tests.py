"Public regression tests for WRAPT-04-DEV; the complete business contract is in materials/WRAPT-04-DEV-contract.md."
import unittest
from wrapt.ttl_cache import ttl_cache

def test_ttl_completion_boundary_lru_and_expired_cleanup():
    "Verify ttl completion boundary lru and expired cleanup."
    clock=[0];calls=[]
    @ttl_cache(5,maxsize=2,clock=lambda:clock[0])
    def value(x):calls.append(x);clock[0]+=2;return x*3
    assert value(1)==3 and clock[0]==2
    clock[0]=6;assert value(1)==3 and calls==[1]
    clock[0]=7;assert value(1)==3 and calls==[1,1]
    value(2);value(3);assert value.cache_info().currsize==2
    clock[0]+=6;assert value.cache_info().currsize==0

def test_zero_policy_errors_and_backward_clock_are_explicit():
    "Verify zero policy errors and backward clock are explicit."
    calls=[]
    @ttl_cache(0,clock=lambda:0)
    def value(x):calls.append(x);return x
    value(1);value(1);assert calls==[1,1] and value.cache_info().currsize==0
    for ttl in (-1,float('nan'),True):
        with unittest.TestCase().assertRaises(ValueError):ttl_cache(ttl)
    clock=[5]
    @ttl_cache(2,clock=lambda:clock[0])
    def f():return 1
    f();clock[0]=4
    with unittest.TestCase().assertRaises(ValueError):f()

