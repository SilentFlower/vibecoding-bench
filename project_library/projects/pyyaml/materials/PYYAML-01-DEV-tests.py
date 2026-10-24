"""合并序列首源优先不依赖Python短字符串身份。"""
import yaml

def test_long_same_keys_first_source_and_explicit_override():
    """独立长字符串同名键合并时保首源，本地声明仍覆盖。@return None。"""
    key='long_field_name_that_must_not_depend_on_interning'
    text='a: &a\n  '+key+': first\nb: &b\n  '+key+': second\nmerged:\n  <<: [*a, *b]\nlocal:\n  <<: [*a, *b]\n  '+key+': explicit\n'
    value=yaml.safe_load(text)
    assert value['merged'][key]=='first' and value['local'][key]=='explicit'

def test_semantically_equal_numeric_keys_and_nested_merge():
    """整数不同字面拼写归一后相同，不能只比原文本。@return None。"""
    text='a: &a {01: first}\nb: &b {1: second}\nc: &c {<<: [*a, *b], z: third}\nmerged: {<<: *c}'
    value=yaml.safe_load(text)
    assert value['merged']=={1:'first','z':'third'}

