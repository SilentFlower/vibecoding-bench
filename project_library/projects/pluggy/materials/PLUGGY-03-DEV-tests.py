"Public regression tests for PLUGGY-03-DEV; the complete business contract is in materials/PLUGGY-03-DEV-contract.md."
import unittest
from pluggy import PluginManager,HookspecMarker,HookimplMarker
spec=HookspecMarker('app');impl=HookimplMarker('app')


class EqualPlugin:
    "Public regression fixture: EqualPlugin."
    __hash__=None
    def __eq__(self,other):return True
    @impl
    def value(self):return 7


def test_equal_instances_register_lookup_unregister_independently():
    "Verify equal instances register lookup unregister independently."
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
    "Verify identity subset and throwing equality never execute eq."
    class Dangerous(EqualPlugin):
        def __eq__(self,other):raise AssertionError('不应比较插件值')
    class Specs:
        @spec
        def value(self):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);a,b=Dangerous(),Dangerous()
    pm.register(a,'a');pm.register(b,'b')
    assert pm.subset_hook_caller('value',[a])()==[7] and pm.hook.value()==[7,7]
    with unittest.TestCase().assertRaises(ValueError):pm.register(a,'alias')

