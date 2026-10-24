"""历史容量只影响稍后重放，实时事件照常交付。"""
import unittest
from pluggy import PluginManager,HookspecMarker,HookimplMarker
spec=HookspecMarker('app');impl=HookimplMarker('app')


def manager():
    """建立真实历史hook。@return PluginManager。"""
    class Specs:
        @spec(historic=True)
        def event(self,value):pass
    pm=PluginManager('app');pm.add_hookspecs(Specs);return pm


def test_capacity_zero_clear_and_parameter_snapshot():
    """末三条按原事件快照重放，上限零仍实时调用。@return None。"""
    pm=manager();pm.hook.event.set_history_limit(3)
    for index in range(5):
        given={'value':index};pm.hook.event.call_historic(kwargs=given);given['value']=99
    seen=[]
    class Plugin:
        @impl
        def event(self,value):seen.append(value)
    pm.register(Plugin(),'first');assert seen==[2,3,4]
    pm.hook.event.set_history_limit(0);pm.hook.event.call_historic(kwargs={'value':5})
    assert seen==[2,3,4,5] and pm.hook.event._call_history==[]
    assert pm.hook.event.clear_history()==0


def test_replay_snapshot_survives_clear_and_selector_failures():
    """重放中清空只影响未来插件，本轮稳定迭代；选择器异常不提交。@return None。"""
    pm=manager()
    for value in (1,2,3):pm.hook.event.call_historic(kwargs={'value':value})
    before=list(pm.hook.event._call_history)
    with unittest.TestCase().assertRaises(ZeroDivisionError):pm.hook.event.clear_history(lambda kwargs:1/0)
    assert pm.hook.event._call_history==before
    seen=[]
    class Plugin:
        @impl
        def event(self,value):
            seen.append(value)
            if value==1:pm.hook.event.clear_history()
    pm.register(Plugin());assert seen==[1,2,3] and pm.hook.event._call_history==[]

