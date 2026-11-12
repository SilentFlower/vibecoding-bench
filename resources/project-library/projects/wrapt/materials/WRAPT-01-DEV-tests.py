"Public regression tests for WRAPT-01-DEV; the complete business contract is in materials/WRAPT-01-DEV-contract.md."
import wrapt

def test_both_classmethod_orders_return_real_class_and_cache_per_class_key():
    "Verify both classmethod orders return real class and cache per class key."
    for reverse in (False,True):
        calls=[]
        def body(cls,x):calls.append((cls,x));return cls.__name__,x
        decorated=classmethod(wrapt.lru_cache(body)) if reverse else wrapt.lru_cache(classmethod(body))
        class Base:label=decorated
        class Child(Base):pass
        assert Base.label(1)==('Base',1) and Child.label(1)==('Child',1)
        assert Child.label(1)==('Child',1) and Base.label(1)==('Base',1)
        assert calls==[(Base,1),(Child,1)]

def test_reverse_first_multiple_subclasses_and_shared_clear_policy():
    "Verify reverse first multiple subclasses and shared clear policy."
    calls=[]
    class Base:
        @wrapt.lru_cache
        @classmethod
        def label(cls,value):calls.append(cls);return cls.__name__+value
    class A(Base):pass
    class B(Base):pass
    assert A.label('x')=='Ax' and Base.label('x')=='Basex' and B.label('x')=='Bx'
    A.label.cache_clear()
    assert B.label('x')=='Bx' and calls==[A,Base,B,B]

def test_proxies_over_same_class_keep_real_instance_identity_and_gc():
    "Verify proxies over same class keep real instance identity and gc."
    import gc
    import weakref
    class Target:pass
    class Proxy(wrapt.BaseObjectProxy):
        def __init__(self,wrapped,factor):super().__init__(wrapped);self._self_factor=factor
        @wrapt.lru_cache
        def compute(self,value):return self._self_factor*value
    first=Proxy(Target,2);second=Proxy(Target,10)
    assert isinstance(first,type) and not issubclass(type(first),type)
    assert first.compute(5)==10 and second.compute(5)==50 and first.compute(5)==10
    reference=weakref.ref(first);del first;gc.collect()
    assert reference() is None and second.compute(5)==50

