"""公开不触碰热度的缓存读取回归。"""
import pytest
from cachetools import Cache,LRUCache,LFUCache,TTLCache

def test_peek_does_not_promote_lru_entry():
    cache=LRUCache(2);cache['a']=1;cache['b']=2
    assert cache.peek('a')==1
    cache['c']=3
    assert 'a' not in cache and 'b' in cache

def test_peek_does_not_increase_lfu_frequency():
    cache=LFUCache(2);cache['a']=1;cache['b']=2
    assert cache['b']==2
    for _ in range(10):
        assert cache.peek('a')==1
    cache['c']=3
    assert 'a' not in cache

def test_expired_entries_are_missing_without_physical_cleanup():
    clock=[0];cache=TTLCache(2,ttl=1,timer=lambda:clock[0]);cache['a']=1;clock[0]=2
    assert cache.peek('a',None) is None and 'a' in cache._Cache__data
    with pytest.raises(KeyError):
        cache.peek('a')

def test_missing_override_is_not_invoked():
    class Loading(Cache):
        def __missing__(self,key):
            raise AssertionError('不应加载')
    cache=Loading(2)
    assert cache.peek('absent','default')=='default'
