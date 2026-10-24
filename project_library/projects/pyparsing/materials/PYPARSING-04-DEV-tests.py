"Public regression tests for PYPARSING-04-DEV; the complete business contract is in materials/PYPARSING-04-DEV-contract.md."
import unittest
from dataclasses import dataclass,field
import pyparsing as pp
from pyparsing.dataclass_results import to_dataclass,ResultMappingError

@dataclass(frozen=True)
class Item:
    "Public regression fixture: Item."
    name:str
    quantity:int
    tags:list[str]=field(default_factory=list)

@dataclass
class Order:
    "Public regression fixture: Order."
    item:Item
    note:str|None=None

def test_named_group_nested_dataclass_and_defaults_keep_types():
    "Verify named group nested dataclass and defaults keep types."
    grammar=pp.Group(pp.Word(pp.alphas)('name')+pp.common.integer('quantity'))('item')
    result=grammar.parse_string('tea 7',parse_all=True)
    value=to_dataclass(result,Order)
    assert value==Order(Item('tea',7)) and value.item.tags==[] and value.note is None
    assert result.as_dict()=={'item':{'name':'tea','quantity':7}}

def test_precise_path_type_extra_missing_and_explicit_non_strict():
    "Verify precise path type extra missing and explicit non strict."
    for data,path in (({'name':'tea'},'$.quantity'),({'name':'tea','quantity':'7'},'$.quantity'),({'name':'tea','quantity':True},'$.quantity'),({'name':'tea','quantity':7,'extra':1},'$.extra')):
        with unittest.TestCase().assertRaises(ResultMappingError) as caught:to_dataclass(data,Item)
        assert caught.exception.path==path
    assert to_dataclass({'name':'tea','quantity':7,'extra':1},Item,strict=False)==Item('tea',7)

