"""历史事件持有调用时映射浅快照，不把后来键替换当原事件。"""
from types import MappingProxyType
from pluggy import PluginManager,HookspecMarker,HookimplMarker
spec=HookspecMarker('app');impl=HookimplMarker('app')


def test_historic_kwargs_mapping_is_frozen_at_call_time():
    """修改调用方映射不影响稍后注册的真实插件。@return None。"""
    class Specs:
        """真实historic协议。"""
        @spec(historic=True)
        def event(self,value):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs)
    given={'value':'at-call-time'};pm.hook.event.call_historic(kwargs=given);given['value']='mutated'
    seen=[]
    class Plugin:
        """稍后安装的插件。"""
        @impl
        def event(self,value):seen.append(value)
    pm.register(Plugin())
    assert seen==['at-call-time']


def test_defaults_custom_mapping_and_nested_values_remain_shallow():
    """只复制键容器，嵌套业务对象身份明确共享。@return None。"""
    class Specs:
        """含默认值的历史协议。"""
        @spec(historic=True)
        def event(self,value='default'):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);nested=[]
    pm.hook.event.call_historic(kwargs=MappingProxyType({'value':nested}));nested.append(1)
    seen=[]
    class Plugin:
        """真实接收嵌套原对象。"""
        @impl
        def event(self,value):seen.append(value)
    pm.register(Plugin())
    assert seen[0] is nested and seen==[[1]]

