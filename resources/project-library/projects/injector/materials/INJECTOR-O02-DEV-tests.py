"Public regression tests for INJECTOR-O02-DEV; the complete business contract is in materials/INJECTOR-O02-DEV-contract.md."
from dataclasses import dataclass
from injector import Injector,inject,noninjectable,CallError,get_bindings,UnknownArgument
import pytest

def test_dataclass_missing_manual_value_and_explicit_kwarg():
    "Verify dataclass missing manual value and explicit kwarg."
    @noninjectable('value')
    @inject
    @dataclass
    class Item:
        "Public regression fixture: Item."
        prefix:str
        value:int
    container=Injector(lambda b:b.bind(str,to='prefix'))
    assert 'value' not in get_bindings(Item.__init__)
    with pytest.raises(CallError):container.get(Item)
    result=container.create_object(Item,additional_kwargs={'value':9});assert (result.prefix,result.value)==('prefix',9)

def test_decorator_order_frozen_kwonly_and_multiple_exclusions():
    "Verify decorator order frozen kwonly and multiple exclusions."
    @inject
    @noninjectable('x','y')
    @dataclass(frozen=True,kw_only=True)
    class Item:
        "Public regression fixture: Item."
        prefix:str
        x:int
        y:int
    result=Injector(lambda b:b.bind(str,to='ok')).create_object(Item,additional_kwargs={'x':2,'y':3})
    assert (result.prefix,result.x,result.y)==('ok',2,3)

def test_inherited_constructor_does_not_mutate_base_and_unknown():
    "Verify inherited constructor does not mutate base and unknown."
    @inject
    class Base:
        "Public regression fixture: Base."
        def __init__(self,x:int):self.x=x
    @noninjectable('x')
    class Child(Base):
        "Public regression fixture: Child."
    assert 'x' in get_bindings(Base.__init__) and 'x' not in get_bindings(Child.__init__)
    with pytest.raises(UnknownArgument):noninjectable('missing')(Child)
