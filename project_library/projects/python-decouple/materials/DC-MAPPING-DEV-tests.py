"Public regression tests for DC-MAPPING-DEV; the complete business contract is in materials/DC-MAPPING-DEV-contract.md."
import pytest
from decouple import MappingCast


def test_pairs_preserve_values():
    "Verify pairs preserve values."
    assert MappingCast()('SQLite3=sqlite://:memory:,"URL=https://x/?a=b,c"') == {'SQLite3': 'sqlite://:memory:', 'URL': 'https://x/?a=b,c'}


def test_casts_and_duplicate_policy():
    "Verify casts and duplicate policy."
    assert MappingCast(key_cast=int, value_cast=int)('1=2,3=4') == {1: 2, 3: 4}
    with pytest.raises(ValueError):
        MappingCast(key_cast=int)('1=a,01=b')
    assert MappingCast(duplicate='last')('a=1,a=2') == {'a': '2'}


def test_json_and_errors():
    "Verify json and errors."
    assert MappingCast(format='json')('{"x": 2, "nested": {"a": true}}') == {'x': 2, 'nested': {'a': True}}
    for value in ['=x', 'missing']:
        with pytest.raises(ValueError):
            MappingCast()(value)
    with pytest.raises(ValueError):
        MappingCast(format='json')('[1,2]')
