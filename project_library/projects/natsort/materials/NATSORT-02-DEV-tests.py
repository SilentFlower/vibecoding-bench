"""缓存保持原生键语义，容量和不可hash回退可观测。"""
import unittest
from natsort import natsort_keygen, ns
from natsort.cached import cached_natsort_keygen


def test_hit_eviction_and_clear():
    """LRU命中、淘汰和清空遵守容量。@return None。"""
    key=cached_natsort_keygen(maxsize=2)
    assert key('a10')==natsort_keygen()('a10')
    key('a10');key('b2');key('c3')
    assert key.cache_info().hits==1 and key.cache_info().currsize==2
    key.cache_clear()
    assert key.cache_info().currsize==0


def test_unhashable_and_policy_isolation():
    """列表不缓存，不同算法的工厂不串结果。@return None。"""
    key=cached_natsort_keygen()
    value=['x2','x10'];before=key(value);value.append('x1')
    assert key(value)!=before
    other=cached_natsort_keygen(alg=ns.REAL)
    assert other('-2.5')==natsort_keygen(alg=ns.REAL)('-2.5')
    with unittest.TestCase().assertRaises(ValueError):cached_natsort_keygen(alg=ns.LOCALE)


def test_exception_is_not_cached():
    """用户key异常保留且不会成为缓存值。@return None。"""
    seen=[]
    def extract(value):
        """模拟首次失败。@param value 原输入。@return 原输入。"""
        seen.append(value)
        if len(seen)==1:raise RuntimeError('once')
        return value
    key=cached_natsort_keygen(key=extract)
    with unittest.TestCase().assertRaises(RuntimeError):key('x4')
    key('x4');key('x4')
    assert len(seen)==2 and key.cache_info().hits==1

