"Public regression tests for PLUGGY-01-DEV; the complete business contract is in materials/PLUGGY-01-DEV-contract.md."
from types import MappingProxyType
from pluggy import PluginManager,HookspecMarker,HookimplMarker
spec=HookspecMarker('app');impl=HookimplMarker('app')


def test_historic_kwargs_mapping_is_frozen_at_call_time():
    "Verify historic kwargs mapping is frozen at call time."
    class Specs:
        "Public regression fixture: Specs."
        @spec(historic=True)
        def event(self,value):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs)
    given={'value':'at-call-time'};pm.hook.event.call_historic(kwargs=given);given['value']='mutated'
    seen=[]
    class Plugin:
        "Public regression fixture: Plugin."
        @impl
        def event(self,value):seen.append(value)
    pm.register(Plugin())
    assert seen==['at-call-time']


def test_defaults_custom_mapping_and_nested_values_remain_shallow():
    "Verify defaults custom mapping and nested values remain shallow."
    class Specs:
        "Public regression fixture: Specs."
        @spec(historic=True)
        def event(self,value='default'):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);nested=[]
    pm.hook.event.call_historic(kwargs=MappingProxyType({'value':nested}));nested.append(1)
    seen=[]
    class Plugin:
        "Public regression fixture: Plugin."
        @impl
        def event(self,value):seen.append(value)
    pm.register(Plugin())
    assert seen[0] is nested and seen==[[1]]

