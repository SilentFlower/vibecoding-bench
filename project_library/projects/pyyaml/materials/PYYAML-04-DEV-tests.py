"Public regression tests for PYYAML-04-DEV; the complete business contract is in materials/PYYAML-04-DEV-contract.md."
import unittest
import yaml
from yaml.tagged import TaggedValue,load_preserving,dump_preserving

def test_scalar_sequence_mapping_roundtrip_without_type_guessing():
    "Verify scalar sequence mapping roundtrip without type guessing."
    value=load_preserving('region: !Region cn\nports: !Ports [80, 443]\nconfig: !Config {active: true}')
    assert value['region']==TaggedValue('!Region','scalar','cn')
    assert value['ports'].value==[80,443] and value['config'].value=={'active':True}
    restored=load_preserving(dump_preserving(value))
    assert restored==value
    with unittest.TestCase().assertRaises(yaml.constructor.ConstructorError):yaml.safe_load('!Region cn')

def test_recursive_alias_and_python_tag_are_nonexecuting_data():
    "Verify recursive alias and python tag are nonexecuting data."
    value=load_preserving('&a !Items [*a]')
    assert value.value[0] is value
    restored=load_preserving(dump_preserving(value))
    assert restored.value[0] is restored
    value=load_preserving('!!python/object/apply:unavailable.module [opaque]')
    assert isinstance(value,TaggedValue) and value.tag.endswith('python/object/apply:unavailable.module')

