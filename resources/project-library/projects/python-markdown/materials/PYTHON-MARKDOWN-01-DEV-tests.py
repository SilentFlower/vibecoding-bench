"Public regression tests for PYTHON-MARKDOWN-01-DEV; the complete business contract is in materials/PYTHON-MARKDOWN-01-DEV-contract.md."
import unittest
from markdown.extensions import Extension


class Configured(Extension):
    "Public regression fixture: Configured."
    config={'label':['default','说明'],'nested':[{'items':[1]},'嵌套'],'enabled':[False,'开关']}


def test_instances_subclass_and_explicit_mutable_values():
    "Verify instances subclass and explicit mutable values."
    first=Configured(label='first');second=Configured()
    assert second.getConfig('label')==Configured.config['label'][0]=='default'
    first.getConfig('nested')['items'].append(2)
    assert second.getConfig('nested')=={'items':[1]}
    given={'items':[9]};third=Configured(nested=given);given['items'].append(10)
    assert third.getConfig('nested')=={'items':[9]}
    class Child(Configured):
        "Public regression fixture: Child."
    assert Child().getConfig('label')=='default'


def test_callbacks_boolean_conversion_and_unknown_keys():
    "Verify callbacks boolean conversion and unknown keys."
    class Callback:
        "Public regression fixture: Callback."
        def __call__(self,value):
            "Support the public regression through __call__."
            return value
        def __deepcopy__(self,memo):
            "Support the public regression through __deepcopy__."
            raise AssertionError('不应复制回调')
    callback=Callback()
    class Custom(Extension):
        "Public regression fixture: Custom."
        config={'callback':[callback,'回调']}
    assert Custom().getConfig('callback') is callback
    assert Configured(enabled='true').getConfig('enabled') is True
    with unittest.TestCase().assertRaises(KeyError):Configured(unknown=1)

