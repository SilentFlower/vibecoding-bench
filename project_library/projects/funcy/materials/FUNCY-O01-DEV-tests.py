"Public regression tests for FUNCY-O01-DEV; the complete business contract is in materials/FUNCY-O01-DEV-contract.md."
from funcy import cached_property,cached_readonly
import pytest

def test_renamed_property_preserves_original_method_and_instance_isolation():
    "Verify renamed property preserves original method and instance isolation."
    class Example:
        "Public regression fixture: Example."
        def __init__(self):self.calls=0
        def calculate(self):self.calls+=1;return self.calls
        value=cached_property(calculate)
    one,two=Example(),Example();assert one.value==one.value==1 and two.value==1
    assert callable(one.calculate) and one.calculate()==2 and one.__dict__['value']==1

def test_manual_set_delete_inheritance_and_readonly():
    "Verify manual set delete inheritance and readonly."
    class Base:
        "Public regression fixture: Base."
        def calc(self):return object()
        value=cached_property(calc)
        fixed=cached_readonly(calc)
    class Child(Base):
        "Public regression fixture: Child."
    obj=Child();value=obj.value;assert obj.value is value
    obj.value=3;assert obj.value==3;del obj.value;assert obj.value is not value
    assert obj.fixed is obj.fixed
    with pytest.raises(AttributeError):obj.fixed=3

def test_conflicting_aliases_and_slot_error():
    "Verify conflicting aliases and slot error."
    property=cached_property(lambda self:1)
    with pytest.raises((RuntimeError,TypeError)):
        class Invalid:
            "Public regression fixture: Invalid."
            a=property;b=property
    class Slots:
        "Public regression fixture: Slots."
        __slots__=()
        value=cached_property(lambda self:1)
    with pytest.raises(AttributeError):Slots().value
