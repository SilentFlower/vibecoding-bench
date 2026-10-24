"Public regression tests for SORTEDCONTAINERS-02-DEV; the complete business contract is in materials/SORTEDCONTAINERS-02-DEV-contract.md."
import unittest
from sortedcontainers import SortedKeyList

def test_refresh_by_old_position_preserves_objects_and_new_order():
    "Verify refresh by old position preserves objects and new order."
    a={'rank':1};b={'rank':2};c={'rank':3}
    values=SortedKeyList([a,b,c],key=lambda item:item['rank']);a['rank']=4
    assert values.refresh_at(0) is a and list(values)==[b,c,a]
    assert values[-1] is a;values._check()
    c['rank']=0;values.refresh_at(-2);assert list(values)==[c,b,a];values._check()

def test_invalid_or_comparison_failure_keeps_existing_cached_index():
    "Verify invalid or comparison failure keeps existing cached index."
    a={'rank':1};b={'rank':2};values=SortedKeyList([a,b],key=lambda item:item['rank'])
    before_keys=[list(block) for block in values._keys]
    a['rank']='bad'
    with unittest.TestCase().assertRaises(TypeError):values.refresh_at(0)
    assert list(values)==[a,b] and values._keys==before_keys
    a['rank']=1;values._check()
    with unittest.TestCase().assertRaises(IndexError):values.refresh_at(20)

