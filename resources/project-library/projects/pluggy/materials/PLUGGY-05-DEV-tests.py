"Public regression tests for PLUGGY-05-DEV; the complete business contract is in materials/PLUGGY-05-DEV-contract.md."
import unittest
from pluggy import PluginManager,HookspecMarker,HookimplMarker
from pluggy.scoped import temporary_plugins
spec=HookspecMarker('app');impl=HookimplMarker('app')


class EqualPlugin:
    "Public regression fixture: EqualPlugin."
    __hash__=None
    def __eq__(self,other):return True
    @impl
    def value(self):return id(self)


def test_scope_keeps_existing_equal_plugins_and_cleans_on_error():
    "Verify scope keeps existing equal plugins and cleans on error."
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
    "Verify preflight and partial historic failure cleanup."
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

