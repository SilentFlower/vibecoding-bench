"Public regression tests for TZ-DISSOC-IN-DEV; the complete business contract is in materials/TZ-DISSOC-IN-DEV-contract.md."
from collections import OrderedDict
import pytest
from toolz import dissoc_in
from toolz.curried import dissoc_in as curried


def test_delete_and_share_untouched():
    "Verify delete and share untouched."
    original = {'account': {'secret': 1, 'name': 'x'}, 'other': {'value': 2}}
    result = dissoc_in(original, ['account', 'secret'])
    assert result == {'account': {'name': 'x'}, 'other': {'value': 2}}
    assert original['account']['secret'] == 1
    assert result['other'] is original['other']
    assert result['account'] is not original['account']


def test_missing_prune_and_factory():
    "Verify missing prune and factory."
    assert dissoc_in({'a': {'b': 1}}, ['a', 'b']) == {'a': {}}
    assert dissoc_in({'a': {'b': 1}}, ['a', 'b'], prune=True) == {}
    with pytest.raises(KeyError):
        dissoc_in({}, ['a'], strict=True)
    assert isinstance(dissoc_in({'a': 1}, ['a'], factory=OrderedDict), OrderedDict)


def test_curried_and_invalid_paths():
    "Verify curried and invalid paths."
    assert curried({'a': 1})(['a']) == {}
    with pytest.raises(ValueError):
        dissoc_in({}, [])
    with pytest.raises(TypeError):
        dissoc_in({'a': 1}, ['a', 'b'])
