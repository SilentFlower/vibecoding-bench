"""实际属性名与函数名不同也应只求值一次，不遮蔽方法。"""
from funcy import cached_property,cached_readonly
import pytest

def test_renamed_property_preserves_original_method_and_instance_isolation():
    """缓存写入value而非calculate。@return None。"""
    class Example:
        """有显式别名的业务对象。"""
        def __init__(self):self.calls=0
        def calculate(self):self.calls+=1;return self.calls
        value=cached_property(calculate)
    one,two=Example(),Example();assert one.value==one.value==1 and two.value==1
    assert callable(one.calculate) and one.calculate()==2 and one.__dict__['value']==1

def test_manual_set_delete_inheritance_and_readonly():
    """普通属性可赋值删除，readonly仍受保护。@return None。"""
    class Base:
        """缓存属性和只读属性共用实际名字协议。"""
        def calc(self):return object()
        value=cached_property(calc)
        fixed=cached_readonly(calc)
    class Child(Base):
        """继承原描述符，不改变绑定名字。"""
    obj=Child();value=obj.value;assert obj.value is value
    obj.value=3;assert obj.value==3;del obj.value;assert obj.value is not value
    assert obj.fixed is obj.fixed
    with pytest.raises(AttributeError):obj.fixed=3

def test_conflicting_aliases_and_slot_error():
    """重用同一描述符异名拒绝，无字典实例不能假装已缓存。@return None。"""
    property=cached_property(lambda self:1)
    with pytest.raises((RuntimeError,TypeError)):
        class Invalid:
            """故意冲突绑定。"""
            a=property;b=property
    class Slots:
        """故意无实例字典。"""
        __slots__=()
        value=cached_property(lambda self:1)
    with pytest.raises(AttributeError):Slots().value
