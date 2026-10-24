"""拒绝的入口点不能污染分发映射或成功计数。"""
from types import SimpleNamespace
from unittest.mock import patch
from pluggy import PluginManager


def distribution(plugin):
    """构造离线元数据夹具，不导入真实第三方插件。@param plugin 返回对象。@return 分发。"""
    entry=SimpleNamespace(group='app',name='entry',value='pkg:plugin',load=lambda:plugin)
    return SimpleNamespace(entry_points=[entry],metadata={'Name':'package'},version='1')


def test_none_or_explicitly_rejected_registration_has_no_dist():
    """None与子类拒绝都必须保持清单可读。@return None。"""
    pm=PluginManager('app')
    with patch('importlib.metadata.distributions',return_value=[distribution(None)]):assert pm.load_setuptools_entrypoints('app')==0
    assert pm.list_plugin_distributions()==[]
    class Rejecting(PluginManager):
        """真实拒绝注册子类。"""
        def register(self,plugin,name=None):return None
    pm=Rejecting('app')
    with patch('importlib.metadata.distributions',return_value=[distribution(object())]):assert pm.load_setuptools_entrypoints('app')==0
    assert pm.list_plugin_distributions()==[]


def test_actual_renamed_plugin_is_used_and_unregister_cleans_dist():
    """不能硬记请求名，按register真实返回名关联。@return None。"""
    class Renaming(PluginManager):
        """支持自定义命名策略的管理器。"""
        def register(self,plugin,name=None):return super().register(plugin,name='renamed')
    plugin=object();dist=distribution(plugin);pm=Renaming('app')
    with patch('importlib.metadata.distributions',return_value=[dist]):assert pm.load_setuptools_entrypoints('app')==1
    assert pm.get_plugin('renamed') is plugin and pm.list_plugin_distributions()==[(plugin,dist)]
    pm.unregister(name='renamed');assert pm.list_plugin_distributions()==[]

