"Public regression tests for INJECTOR-O01-DEV; the complete business contract is in materials/INJECTOR-O01-DEV-contract.md."
from injector import Injector,BoundKey,InstanceProvider,inject,NoInject,CallError
import pytest

def test_partial_bound_constructor_still_injects_and_keeps_explicit():
    "Verify partial bound constructor still injects and keeps explicit."
    class Item:
        "Public regression fixture: Item."
        @inject
        def __init__(self,prefix:str,value:int):self.text=prefix+str(value)
    container=Injector(lambda b:b.bind(str,to='item:'))
    result=container.get(BoundKey(Item,value=InstanceProvider(7)))
    assert result.text=='item:7'

def test_nested_boundkey_outer_priority_and_provider_once():
    "Verify nested boundkey outer priority and provider once."
    class Item:
        "Public regression fixture: Item."
        @inject
        def __init__(self,prefix:str,value:int=1):self.text=prefix+str(value)
    calls=[];container=Injector(lambda b:b.bind(str,to='prefix:'))
    inner=BoundKey(Item,value=InstanceProvider(1));outer=BoundKey(inner,value=lambda:calls.append(1) or 9)
    assert container.get(outer).text=='prefix:9' and calls==[1]

def test_noninject_constructor_noinject_and_provider_error():
    "Verify noninject constructor noinject and provider error."
    class Plain:
        "Public regression fixture: Plain."
        def __init__(self,value):self.value=value
    assert Injector().get(BoundKey(Plain,value=InstanceProvider('given'))).value=='given'
    class Manual:
        "Public regression fixture: Manual."
        @inject
        def __init__(self,value:NoInject[int]):self.value=value
    with pytest.raises(CallError):Injector().get(BoundKey(Manual))
    def fail():raise ValueError('provider')
    with pytest.raises(ValueError):Injector().get(BoundKey(Plain,value=fail))
