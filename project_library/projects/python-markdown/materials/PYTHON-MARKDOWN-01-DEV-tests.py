"""扩展类级配置是默认模板，实例不得相互污染。"""
import unittest
from markdown.extensions import Extension


class Configured(Extension):
    """模拟官方允许的类级配置模式。"""
    config={'label':['default','说明'],'nested':[{'items':[1]},'嵌套'],'enabled':[False,'开关']}


def test_instances_subclass_and_explicit_mutable_values():
    """首实例赋值、嵌套修改及调用方容器均隔离。@return None。"""
    first=Configured(label='first');second=Configured()
    assert second.getConfig('label')==Configured.config['label'][0]=='default'
    first.getConfig('nested')['items'].append(2)
    assert second.getConfig('nested')=={'items':[1]}
    given={'items':[9]};third=Configured(nested=given);given['items'].append(10)
    assert third.getConfig('nested')=={'items':[9]}
    class Child(Configured):
        """继承默认模板仍须独立。"""
    assert Child().getConfig('label')=='default'


def test_callbacks_boolean_conversion_and_unknown_keys():
    """不盲目deepcopy回调，原bool/未知键合同保持。@return None。"""
    class Callback:
        """不允许复制的可调用配置对象。"""
        def __call__(self,value):
            """原样回传。@param value 值。@return 原值。"""
            return value
        def __deepcopy__(self,memo):
            """确保实现没有复制任意业务对象。@param memo 缓存。@return 不返回。"""
            raise AssertionError('不应复制回调')
    callback=Callback()
    class Custom(Extension):
        """带自定义回调的扩展。"""
        config={'callback':[callback,'回调']}
    assert Custom().getConfig('callback') is callback
    assert Configured(enabled='true').getConfig('enabled') is True
    with unittest.TestCase().assertRaises(KeyError):Configured(unknown=1)

