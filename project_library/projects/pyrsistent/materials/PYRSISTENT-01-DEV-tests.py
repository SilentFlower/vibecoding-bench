"""嵌套映射导入时ignore_extra不能在中途丢失。"""
import unittest
from pyrsistent import PClass,PRecord,CheckedPMap,field,pmap_field,pvector_field


class Item(PClass):
    """真实受校验商品。"""
    quantity=field(type=int,mandatory=True)


class Items(CheckedPMap):
    """值应递归构造为Item。"""
    __key_type__=str
    __value_type__=Item


def test_map_and_optional_record_propagate_declared_policy():
    """额外展示字段按True忽略、默认仍拒绝。@return None。"""
    raw={'a':{'quantity':2,'label':'display'}}
    assert Items.create(raw,ignore_extra=True)['a']==Item(quantity=2)
    with unittest.TestCase().assertRaises(AttributeError):Items.create(raw)
    class Record(PRecord):
        """可选映射组合。"""
        items=pmap_field(str,Item,optional=True)
    assert Record.create({'items':raw},ignore_extra=True)['items']['a'].quantity==2
    assert Record.create({'items':None},ignore_extra=True)['items'] is None


def test_existing_instances_and_type_errors_are_not_replaced():
    """已有实例复用、非额外字段错误不能吞掉。@return None。"""
    item=Item(quantity=2);items=Items({'a':item})
    assert Items.create(items,ignore_extra=True) is items
    assert Items.create({'a':item},ignore_extra=True)['a'] is item
    with unittest.TestCase().assertRaises(TypeError):Items.create({'a':{'quantity':'wrong','label':'x'}},ignore_extra=True)

