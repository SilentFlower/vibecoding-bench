"""format必须穿过Checked容器到达记录字段serializer。"""
from pyrsistent import PRecord,CheckedPMap,CheckedPVector,CheckedPSet,field


class Item(PRecord):
    """按format决定输出文本的业务值。"""
    quantity=field(type=int,serializer=lambda format,value:str(format)+':'+str(value))


class Items(CheckedPMap):
    """真实受校验映射。"""
    __key_type__=str
    __value_type__=Item


def test_nested_map_and_vector_receive_the_same_format():
    """同对象直接和嵌套序列化政策一致。@return None。"""
    class Sequence(CheckedPVector):
        """受校验序列。"""
        __type__=Item
    item=Item(quantity=2)
    assert item.serialize('json')=={'quantity':'json:2'}
    assert Items({'a':item}).serialize('json')=={'a':{'quantity':'json:2'}}
    assert Sequence([item]).serialize('json')==[{'quantity':'json:2'}]


def test_custom_container_serializer_retains_authority_and_default():
    """显式自定义serializer不被覆盖，None默认按原值传递。@return None。"""
    class Custom(Items):
        """容器自己的序列化策略。"""
        def __serializer__(self,format,key,value):
            """明确接管键值输出。@param format 格式。@param key 键。@param value 值。@return 一对。"""
            return key,str(format)+':custom'
    item=Item(quantity=3)
    assert Custom({'a':item}).serialize('wire')=={'a':'wire:custom'}
    assert Items({'a':item}).serialize()=={'a':{'quantity':'None:3'}}

