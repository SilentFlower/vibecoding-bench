"""类级排除注入真正作用于最终dataclass构造。"""
from dataclasses import dataclass
from injector import Injector,inject,noninjectable,CallError,get_bindings,UnknownArgument
import pytest

def test_dataclass_missing_manual_value_and_explicit_kwarg():
    """缺少非注入值明确失败，调用方给值后其他依赖注入。@return None。"""
    @noninjectable('value')
    @inject
    @dataclass
    class Item:
        """有服务及手动参数的数据类。"""
        prefix:str
        value:int
    container=Injector(lambda b:b.bind(str,to='prefix'))
    assert 'value' not in get_bindings(Item.__init__)
    with pytest.raises(CallError):container.get(Item)
    result=container.create_object(Item,additional_kwargs={'value':9});assert (result.prefix,result.value)==('prefix',9)

def test_decorator_order_frozen_kwonly_and_multiple_exclusions():
    """装饰器两种顺序及kw-only数据类都保留排除集合。@return None。"""
    @inject
    @noninjectable('x','y')
    @dataclass(frozen=True,kw_only=True)
    class Item:
        """冻结且仅关键字参数的数据类。"""
        prefix:str
        x:int
        y:int
    result=Injector(lambda b:b.bind(str,to='ok')).create_object(Item,additional_kwargs={'x':2,'y':3})
    assert (result.prefix,result.x,result.y)==('ok',2,3)

def test_inherited_constructor_does_not_mutate_base_and_unknown():
    """子类排除不能污染基类共享函数元数据。@return None。"""
    @inject
    class Base:
        """原可注入构造。"""
        def __init__(self,x:int):self.x=x
    @noninjectable('x')
    class Child(Base):
        """只限制自身构造。"""
    assert 'x' in get_bindings(Base.__init__) and 'x' not in get_bindings(Child.__init__)
    with pytest.raises(UnknownArgument):noninjectable('missing')(Child)
