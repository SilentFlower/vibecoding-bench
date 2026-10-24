"""已变业务rank通过显式刷新恢复索引，不用新键寻找旧位置。"""
import unittest
from sortedcontainers import SortedKeyList

def test_refresh_by_old_position_preserves_objects_and_new_order():
    """按旧索引移除后重插，未变对象不被复制。@return None。"""
    a={'rank':1};b={'rank':2};c={'rank':3}
    values=SortedKeyList([a,b,c],key=lambda item:item['rank']);a['rank']=4
    assert values.refresh_at(0) is a and list(values)==[b,c,a]
    assert values[-1] is a;values._check()
    c['rank']=0;values.refresh_at(-2);assert list(values)==[c,b,a];values._check()

def test_invalid_or_comparison_failure_keeps_existing_cached_index():
    """错误不提交半成品，也不掩盖调用方已改业务对象。@return None。"""
    a={'rank':1};b={'rank':2};values=SortedKeyList([a,b],key=lambda item:item['rank'])
    before_keys=[list(block) for block in values._keys]
    a['rank']='bad'
    with unittest.TestCase().assertRaises(TypeError):values.refresh_at(0)
    assert list(values)==[a,b] and values._keys==before_keys
    a['rank']=1;values._check()
    with unittest.TestCase().assertRaises(IndexError):values.refresh_at(20)

