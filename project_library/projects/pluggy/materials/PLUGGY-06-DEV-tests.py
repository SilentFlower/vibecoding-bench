"Public regression tests for PLUGGY-06-DEV; the complete business contract is in materials/PLUGGY-06-DEV-contract.md."
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from pluggy import PluginManager
from pluggy.discovery import discover_entrypoints,load_entrypoint


def fixture():
    "Support the public regression through fixture."
    calls=[];plugin=object()
    entries=[SimpleNamespace(group='app',name=name,value='pkg:'+name,load=lambda name=name:calls.append(name) or plugin) for name in ('one','two')]
    return SimpleNamespace(metadata={'Name':'package'},version='1',entry_points=entries),calls,plugin


def test_preview_then_only_one_selected_plugin_loads():
    "Verify preview then only one selected plugin loads."
    dist,calls,plugin=fixture();pm=PluginManager('app')
    with patch('importlib.metadata.distributions',return_value=[dist]):
        report=discover_entrypoints('app')
        assert [row.name for row in report.candidates]==['one','two'] and calls==[] and report.errors==()
        assert load_entrypoint(pm,report.candidates[1])=='two'
    assert calls==['two'] and pm.list_plugin_distributions()==[(plugin,dist)]


def test_changed_blocked_and_bad_metadata_never_import():
    "Verify changed blocked and bad metadata never import."
    dist,calls,plugin=fixture();pm=PluginManager('app')
    with patch('importlib.metadata.distributions',return_value=[dist]):candidate=discover_entrypoints('app').candidates[0]
    dist.version='2'
    with patch('importlib.metadata.distributions',return_value=[dist]):
        with unittest.TestCase().assertRaises(ValueError):load_entrypoint(pm,candidate)
        pm.set_blocked('one');assert load_entrypoint(pm,candidate) is None
    assert calls==[]
    with patch('importlib.metadata.distributions',return_value=[SimpleNamespace(metadata={},version='1',entry_points=[])]):
        report=discover_entrypoints('app');assert report.candidates==() and report.errors

