"""键值配置映射保留URL中的等号并检查重复键。"""
import pytest
from decouple import MappingCast


def test_pairs_preserve_values():
    """只分割首个等号，引号内部逗号不拆项。@return None。"""
    assert MappingCast()('SQLite3=sqlite://:memory:,"URL=https://x/?a=b,c"') == {'SQLite3': 'sqlite://:memory:', 'URL': 'https://x/?a=b,c'}


def test_casts_and_duplicate_policy():
    """在键转换后检查重复，支持显式末项获胜。@return None。"""
    assert MappingCast(key_cast=int, value_cast=int)('1=2,3=4') == {1: 2, 3: 4}
    with pytest.raises(ValueError):
        MappingCast(key_cast=int)('1=a,01=b')
    assert MappingCast(duplicate='last')('a=1,a=2') == {'a': '2'}


def test_json_and_errors():
    """JSON必须为对象，空键或无等号明确失败。@return None。"""
    assert MappingCast(format='json')('{"x": 2, "nested": {"a": true}}') == {'x': 2, 'nested': {'a': True}}
    for value in ['=x', 'missing']:
        with pytest.raises(ValueError):
            MappingCast()(value)
    with pytest.raises(ValueError):
        MappingCast(format='json')('[1,2]')
