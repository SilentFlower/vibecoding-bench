"""无字典实例可以真正缓存且外置条目不保活self。"""
import gc
import weakref
import unittest
from wrapt.weak_cache import weak_method_cache

def test_slotted_unhashable_instances_are_isolated_and_released():
    """id身份不依赖hash/equality，原方法无强引用存入缓存。@return None。"""
    class Item:
        __slots__=('factor','calls','__weakref__')
        __hash__=None
        def __init__(self,factor):self.factor=factor;self.calls=0
        @weak_method_cache(maxsize=2)
        def value(self,x):self.calls+=1;return self.factor*x
    first=Item(2);second=Item(3)
    assert first.value(4)==first.value(4)==8 and second.value(4)==12
    assert first.calls==second.calls==1 and Item.value.cache_count()==2
    reference=weakref.ref(first);del first;gc.collect()
    assert reference() is None and Item.value.cache_count()==1
    Item.value.cache_clear(second);second.value(4);assert second.calls==2

def test_nonweakrefable_objects_reject_and_exceptions_are_not_cached():
    """无法弱引用明确失败，不退化为泄漏强存储。@return None。"""
    class NoWeak:
        __slots__=()
        @weak_method_cache()
        def value(self):return 1
    with unittest.TestCase().assertRaises(TypeError):NoWeak().value()
    class Item:
        def __init__(self):self.calls=0
        @weak_method_cache()
        def fail(self):self.calls+=1;raise ValueError('business')
    item=Item()
    for _ in range(2):
        with unittest.TestCase().assertRaises(ValueError):item.fail()
    assert item.calls==2

