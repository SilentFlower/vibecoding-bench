"Public regression tests for PLUGGY-02-DEV; the complete business contract is in materials/PLUGGY-02-DEV-contract.md."
from types import SimpleNamespace
from unittest.mock import patch
from pluggy import PluginManager


def distribution(plugin):
    "Support the public regression through distribution."
    entry=SimpleNamespace(group='app',name='entry',value='pkg:plugin',load=lambda:plugin)
    return SimpleNamespace(entry_points=[entry],metadata={'Name':'package'},version='1')


def test_none_or_explicitly_rejected_registration_has_no_dist():
    "Verify none or explicitly rejected registration has no dist."
    pm=PluginManager('app')
    with patch('importlib.metadata.distributions',return_value=[distribution(None)]):assert pm.load_setuptools_entrypoints('app')==0
    assert pm.list_plugin_distributions()==[]
    class Rejecting(PluginManager):
        "Public regression fixture: Rejecting."
        def register(self,plugin,name=None):return None
    pm=Rejecting('app')
    with patch('importlib.metadata.distributions',return_value=[distribution(object())]):assert pm.load_setuptools_entrypoints('app')==0
    assert pm.list_plugin_distributions()==[]


def test_actual_renamed_plugin_is_used_and_unregister_cleans_dist():
    "Verify actual renamed plugin is used and unregister cleans dist."
    class Renaming(PluginManager):
        "Public regression fixture: Renaming."
        def register(self,plugin,name=None):return super().register(plugin,name='renamed')
    plugin=object();dist=distribution(plugin);pm=Renaming('app')
    with patch('importlib.metadata.distributions',return_value=[dist]):assert pm.load_setuptools_entrypoints('app')==1
    assert pm.get_plugin('renamed') is plugin and pm.list_plugin_distributions()==[(plugin,dist)]
    pm.unregister(name='renamed');assert pm.list_plugin_distributions()==[]

