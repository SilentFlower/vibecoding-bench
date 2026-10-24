"Public regression tests for TZ-UPDATE-ONLY-DEV; the complete business contract is in materials/TZ-UPDATE-ONLY-DEV-contract.md."
import pytest
from toolz import update_in


def test_missing_never_calls_function():
    "Verify missing never calls function."
    original = {'a': {'b': 1}}
    calls = []
    for path in (['a', 'missing'], ['missing', 'b']):
        result = update_in(original, path, lambda value: calls.append(value), create=False)
        assert result == original and result is not original
    assert calls == []


def test_none_is_existing_and_curried():
    "Verify none is existing and curried."
    from toolz.curried import update_in as curried
    assert update_in({'a': None}, ['a'], lambda value: value is None, create=False) == {'a': True}
    assert curried({'a': 1}, ['a'])(lambda value: value + 1, create=False) == {'a': 2}


def test_default_upsert_and_error():
    "Verify default upsert and error."
    assert update_in({}, ['a', 'b'], lambda value: value + 1, default=0) == {'a': {'b': 1}}
    with pytest.raises(ValueError):
        update_in({}, [], lambda value: value, create=False)
