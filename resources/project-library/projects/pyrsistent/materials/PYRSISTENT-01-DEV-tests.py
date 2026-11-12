"Public regression tests for PYRSISTENT-01-DEV; the complete business contract is in materials/PYRSISTENT-01-DEV-contract.md."
import unittest
from pyrsistent import PClass,PRecord,CheckedPMap,field,pmap_field,pvector_field


class Item(PClass):
    "Public regression fixture: Item."
    quantity=field(type=int,mandatory=True)


class Items(CheckedPMap):
    "Public regression fixture: Items."
    __key_type__=str
    __value_type__=Item


def test_map_and_optional_record_propagate_declared_policy():
    "Verify map and optional record propagate declared policy."
    raw={'a':{'quantity':2,'label':'display'}}
    assert Items.create(raw,ignore_extra=True)['a']==Item(quantity=2)
    with unittest.TestCase().assertRaises(AttributeError):Items.create(raw)
    class Record(PRecord):
        "Public regression fixture: Record."
        items=pmap_field(str,Item,optional=True)
    assert Record.create({'items':raw},ignore_extra=True)['items']['a'].quantity==2
    assert Record.create({'items':None},ignore_extra=True)['items'] is None


def test_existing_instances_and_type_errors_are_not_replaced():
    "Verify existing instances and type errors are not replaced."
    item=Item(quantity=2);items=Items({'a':item})
    assert Items.create(items,ignore_extra=True) is items
    assert Items.create({'a':item},ignore_extra=True)['a'] is item
    with unittest.TestCase().assertRaises(TypeError):Items.create({'a':{'quantity':'wrong','label':'x'}},ignore_extra=True)

