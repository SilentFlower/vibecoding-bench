"""映射排序不修改来源，重复比较值保持输入顺序。"""
from types import MappingProxyType
import pydash

def test_key_and_value_sort_preserve_mapping_and_ties():
    """按客户键与金额排序是两种明确语义。@return None。"""
    source={'b':2,'a':1,'c':2};snapshot=list(source.items())
    assert list(pydash.sort_dict_by_keys(source))==['a','b','c']
    assert list(pydash.sort_dict_by_values(source,reverse=True))==['b','c','a']
    assert list(source.items())==snapshot

def test_custom_mapping_falsey_key_and_transform():
    """Falsey函数仍需应用，不以truthiness跳过。@return None。"""
    class Key:
        """按字符串长度排序。"""
        def __bool__(self):return False
        def __call__(self,value):return len(value)
    source=MappingProxyType({'long':3,'x':2,'xx':1})
    assert list(pydash.sort_dict_by_keys(source,key=Key()))==['x','xx','long']
    assert list(pydash.sort_dict_by_values({1:'BBB',2:'a'},key=str.lower))==[2,1]
    assert pydash.sort_dict_by_values({})=={}

