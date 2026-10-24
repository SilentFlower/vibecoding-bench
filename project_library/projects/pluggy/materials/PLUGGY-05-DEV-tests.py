"""临时插件正常、异常及部分注册失败都不会遗留本轮对象。"""
import unittest
from pluggy import PluginManager,HookspecMarker,HookimplMarker
from pluggy.scoped import temporary_plugins
spec=HookspecMarker('app');impl=HookimplMarker('app')


class EqualPlugin:
    """同值但不同身份的真实插件。"""
    __hash__=None
    def __eq__(self,other):return True
    @impl
    def value(self):return id(self)


def test_scope_keeps_existing_equal_plugins_and_cleans_on_error():
    """依赖前置身份修复，不误删既有相等对象。@return None。"""
    class Specs:
        @spec
        def value(self):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);old,a,b=EqualPlugin(),EqualPlugin(),EqualPlugin();pm.register(old,'old')
    with unittest.TestCase().assertRaises(RuntimeError):
        with temporary_plugins(pm,[('a',a),('b',b)]):
            assert set(pm.hook.value())=={id(old),id(a),id(b)}
            raise RuntimeError('body failed')
    assert pm.list_name_plugin()==[('old',old)] and pm.hook.value()==[id(old)]


def test_preflight_and_partial_historic_failure_cleanup():
    """冲突先拒绝；失败的本轮重放注册也清理。@return None。"""
    class Specs:
        @spec(historic=True)
        def event(self):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);pm.hook.event.call_historic()
    class Broken:
        @impl
        def event(self):raise ValueError('replay failed')
    good=object()
    with unittest.TestCase().assertRaises(ValueError):
        with temporary_plugins(pm,[('good',good),('bad',Broken())]):pass
    assert not pm.has_plugin('good') and not pm.has_plugin('bad') and pm.hook.event.get_hookimpls()==[]

