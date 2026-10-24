"""命名结果映射真实数据类，缺失/额外/类型错误有业务路径。"""
import unittest
from dataclasses import dataclass,field
import pyparsing as pp
from pyparsing.dataclass_results import to_dataclass,ResultMappingError

@dataclass(frozen=True)
class Item:
    """类型转换在语法动作完成。"""
    name:str
    quantity:int
    tags:list[str]=field(default_factory=list)

@dataclass
class Order:
    """嵌套命名结果。"""
    item:Item
    note:str|None=None

def test_named_group_nested_dataclass_and_defaults_keep_types():
    """真实parse结果不是调用方预先构造的dict。@return None。"""
    grammar=pp.Group(pp.Word(pp.alphas)('name')+pp.common.integer('quantity'))('item')
    result=grammar.parse_string('tea 7',parse_all=True)
    value=to_dataclass(result,Order)
    assert value==Order(Item('tea',7)) and value.item.tags==[] and value.note is None
    assert result.as_dict()=={'item':{'name':'tea','quantity':7}}

def test_precise_path_type_extra_missing_and_explicit_non_strict():
    """不把字符串或bool强转int，严格模式不吞字段。@return None。"""
    for data,path in (({'name':'tea'},'$.quantity'),({'name':'tea','quantity':'7'},'$.quantity'),({'name':'tea','quantity':True},'$.quantity'),({'name':'tea','quantity':7,'extra':1},'$.extra')):
        with unittest.TestCase().assertRaises(ResultMappingError) as caught:to_dataclass(data,Item)
        assert caught.exception.path==path
    assert to_dataclass({'name':'tea','quantity':7,'extra':1},Item,strict=False)==Item('tea',7)

