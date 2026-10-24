"""BoundKey只预设业务值，剩余真实构造依赖仍由容器装配。"""
from injector import Injector,BoundKey,InstanceProvider,inject,NoInject,CallError
import pytest

def test_partial_bound_constructor_still_injects_and_keeps_explicit():
    """未提供前缀注入，预设value不被默认注入覆盖。@return None。"""
    class Item:
        """真实可注入业务对象。"""
        @inject
        def __init__(self,prefix:str,value:int):self.text=prefix+str(value)
    container=Injector(lambda b:b.bind(str,to='item:'))
    result=container.get(BoundKey(Item,value=InstanceProvider(7)))
    assert result.text=='item:7'

def test_nested_boundkey_outer_priority_and_provider_once():
    """嵌套声明先合并再求值，外层覆盖内层。@return None。"""
    class Item:
        """带默认业务参数的对象。"""
        @inject
        def __init__(self,prefix:str,value:int=1):self.text=prefix+str(value)
    calls=[];container=Injector(lambda b:b.bind(str,to='prefix:'))
    inner=BoundKey(Item,value=InstanceProvider(1));outer=BoundKey(inner,value=lambda:calls.append(1) or 9)
    assert container.get(outer).text=='prefix:9' and calls==[1]

def test_noninject_constructor_noinject_and_provider_error():
    """非inject构造只接预设值，NoInject缺参和原provider错误不能被掩盖。@return None。"""
    class Plain:
        """普通无注入构造。"""
        def __init__(self,value):self.value=value
    assert Injector().get(BoundKey(Plain,value=InstanceProvider('given'))).value=='given'
    class Manual:
        """明确不注入参数。"""
        @inject
        def __init__(self,value:NoInject[int]):self.value=value
    with pytest.raises(CallError):Injector().get(BoundKey(Manual))
    def fail():raise ValueError('provider')
    with pytest.raises(ValueError):Injector().get(BoundKey(Plain,value=fail))
