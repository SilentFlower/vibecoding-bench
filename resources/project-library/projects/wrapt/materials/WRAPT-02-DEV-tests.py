"Public regression tests for WRAPT-02-DEV; the complete business contract is in materials/WRAPT-02-DEV-contract.md."
import gc
import weakref
import unittest
from wrapt.weak_cache import weak_method_cache

def test_slotted_unhashable_instances_are_isolated_and_released():
    "Verify slotted unhashable instances are isolated and released."
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
    "Verify nonweakrefable objects reject and exceptions are not cached."
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

