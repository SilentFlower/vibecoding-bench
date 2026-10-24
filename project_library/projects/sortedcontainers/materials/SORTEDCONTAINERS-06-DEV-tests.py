"""映射区间直接返回业务items/values，仍按键排序。"""
from operator import neg
from sortedcontainers import SortedDict

def test_item_value_ranges_exactly_match_irange_bounds():
    """边界、顺序和对象身份与已有irange一致。@return None。"""
    payload=[];source=SortedDict({1:'a',2:payload,3:None,4:'d'})
    assert list(source.irange_items(2,4,(True,False)))==[(2,payload),(3,None)]
    assert list(source.irange_values(2,4,(True,False)))==[payload,None]
    assert next(source.irange_values(2,2)) is payload
    assert list(source.irange(2,4))==[2,3,4]

def test_lazy_live_values_reverse_key_and_empty_mapping():
    """创建后读取时取当前value，不把值排序误作键排序。@return None。"""
    source=SortedDict(neg,{1:'b',2:'a',3:'c'});items=source.irange_items(3,1,reverse=True)
    source[2]='updated'
    assert list(items)==[(1,'b'),(2,'updated'),(3,'c')]
    assert list(source.irange_values(3,2))==['c','updated']
    assert list(SortedDict().irange_items())==[]

