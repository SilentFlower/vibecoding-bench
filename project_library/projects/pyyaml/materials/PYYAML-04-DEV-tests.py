"""未知标签可编辑读回，但python/object仍只是数据。"""
import unittest
import yaml
from yaml.tagged import TaggedValue,load_preserving,dump_preserving

def test_scalar_sequence_mapping_roundtrip_without_type_guessing():
    """未知scalar保原文，普通嵌套safe类型仍构造。@return None。"""
    value=load_preserving('region: !Region cn\nports: !Ports [80, 443]\nconfig: !Config {active: true}')
    assert value['region']==TaggedValue('!Region','scalar','cn')
    assert value['ports'].value==[80,443] and value['config'].value=={'active':True}
    restored=load_preserving(dump_preserving(value))
    assert restored==value
    with unittest.TestCase().assertRaises(yaml.constructor.ConstructorError):yaml.safe_load('!Region cn')

def test_recursive_alias_and_python_tag_are_nonexecuting_data():
    """递归标签身份保留，Python标签绝不导入对象。@return None。"""
    value=load_preserving('&a !Items [*a]')
    assert value.value[0] is value
    restored=load_preserving(dump_preserving(value))
    assert restored.value[0] is restored
    value=load_preserving('!!python/object/apply:unavailable.module [opaque]')
    assert isinstance(value,TaggedValue) and value.tag.endswith('python/object/apply:unavailable.module')

