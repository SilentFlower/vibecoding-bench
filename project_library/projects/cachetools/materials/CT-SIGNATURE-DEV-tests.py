"""公开函数签名缓存键回归。"""
import pytest
from cachetools import cached,LRUCache
from cachetools.keys import signature_key

def test_equivalent_calls_and_defaults_share_cache_entry():
    calls=[]
    def work(a,b=2):
        calls.append(1)
        return a+b
    wrapped=cached(LRUCache(8),key=signature_key(work))(work)
    assert wrapped(1)==wrapped(a=1,b=2)==wrapped(1,2)==3 and len(calls)==1

def test_variadic_keyword_order_is_normalized_and_types_are_optional():
    def work(*args,**kwargs):
        pass
    key=signature_key(work,typed=True)
    assert key(1,a=2,b=3)==key(1,b=3,a=2) and key(1)!=key(1.0)

def test_function_namespace_and_explicit_receiver_ignoring():
    def first(self,value=1):
        pass
    def second(self,value=1):
        pass
    assert signature_key(first)(None)!=signature_key(second)(None)
    assert signature_key(first,ignore=('self',))(object(),2)==signature_key(first,ignore=('self',))(object(),value=2)

def test_invalid_binding_unhashable_values_and_unknown_ignore_fail():
    def work(value):
        pass
    key=signature_key(work)
    with pytest.raises(TypeError):
        key()
    with pytest.raises(TypeError):
        key([])
    with pytest.raises(ValueError):
        signature_key(work,ignore=('missing',))
