"Public regression tests for PYYAML-01-DEV; the complete business contract is in materials/PYYAML-01-DEV-contract.md."
import yaml

def test_long_same_keys_first_source_and_explicit_override():
    "Verify long same keys first source and explicit override."
    key='long_field_name_that_must_not_depend_on_interning'
    text='a: &a\n  '+key+': first\nb: &b\n  '+key+': second\nmerged:\n  <<: [*a, *b]\nlocal:\n  <<: [*a, *b]\n  '+key+': explicit\n'
    value=yaml.safe_load(text)
    assert value['merged'][key]=='first' and value['local'][key]=='explicit'

def test_semantically_equal_numeric_keys_and_nested_merge():
    "Verify semantically equal numeric keys and nested merge."
    text='a: &a {01: first}\nb: &b {1: second}\nc: &c {<<: [*a, *b], z: third}\nmerged: {<<: *c}'
    value=yaml.safe_load(text)
    assert value['merged']=={1:'first','z':'third'}

