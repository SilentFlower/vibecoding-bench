"""插件是对象身份，不能被用户__eq__重定义注册关系。"""
import unittest
from pluggy import PluginManager,HookspecMarker,HookimplMarker
spec=HookspecMarker('app');impl=HookimplMarker('app')


class EqualPlugin:
    """相同业务值但独立实例。"""
    __hash__=None
    def __eq__(self,other):return True
    @impl
    def value(self):return 7


def test_equal_instances_register_lookup_unregister_independently():
    """两个相等且不可hash对象使用不同名字仍可管理。@return None。"""
    class Specs:
        @spec
        def value(self):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);a,b,c=EqualPlugin(),EqualPlugin(),EqualPlugin()
    pm.register(a,'a');pm.register(b,'b')
    assert pm.get_name(a)=='a' and pm.get_name(b)=='b' and pm.get_name(c) is None
    assert not pm.is_registered(c) and pm.hook.value()==[7,7]
    pm.unregister(a)
    assert pm.get_name(b)=='b' and pm.hook.value()==[7]


def test_identity_subset_and_throwing_equality_never_execute_eq():
    """子集及重复同对象校验都用is，不吞用户eq异常。@return None。"""
    class Dangerous(EqualPlugin):
        def __eq__(self,other):raise AssertionError('不应比较插件值')
    class Specs:
        @spec
        def value(self):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);a,b=Dangerous(),Dangerous()
    pm.register(a,'a');pm.register(b,'b')
    assert pm.subset_hook_caller('value',[a])()==[7] and pm.hook.value()==[7,7]
    with unittest.TestCase().assertRaises(ValueError):pm.register(a,'alias')

