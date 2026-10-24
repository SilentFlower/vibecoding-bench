"""最近计划查询尊重key顺序，None可为明确缺项默认。"""
import unittest
from operator import neg
from sortedcontainers import SortedList,SortedSet,SortedDict

def test_all_four_neighbors_and_mapping_item_identity():
    """等值与严格邻居不能混用，映射返回业务item。@return None。"""
    for source in (SortedList([1,3,5]),SortedSet([1,3,5])):
        assert source.floor(4)==3 and source.ceil(4)==5 and source.lower(3)==1 and source.higher(3)==5
        assert source.floor(3)==3 and source.ceil(3)==3
    value=[];source=SortedDict({1:'a',3:value,5:'c'})
    assert source.floor(4)==(3,value) and source.floor(4)[1] is value

def test_duplicate_keys_reverse_order_and_explicit_default():
    """缺项不能默认用None掩盖，方向由排序策略决定。@return None。"""
    values=SortedList([1,3,5],key=neg)
    assert values.floor(4)==5 and values.ceil(4)==3
    assert values.lower(3)==5 and values.higher(3)==1
    assert values.floor(8,None) is None
    with unittest.TestCase().assertRaises(KeyError):SortedList().ceil(1)
    values=SortedList([(2,'a'),(2,'b'),(4,'c')],key=lambda item:item[0])
    assert values.floor((2,'probe'))==(2,'b') and values.ceil((2,'probe'))==(2,'a')

