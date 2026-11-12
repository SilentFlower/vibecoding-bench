"Public regression tests for TZ-KEYMAP-DEV; the complete business contract is in materials/TZ-KEYMAP-DEV-contract.md."
import pytest
from toolz import keymap


def test_collision_policies():
    "Verify collision policies."
    values = {'A': 1, 'a': 2}
    assert keymap(str.lower, values) == {'a': 2}
    assert keymap(str.lower, values, collision='first') == {'a': 1}
    with pytest.raises(ValueError):
        keymap(str.lower, values, collision='error')
    assert values == {'A': 1, 'a': 2}


def test_combiner_and_once():
    "Verify combiner and once."
    calls = []
    assert keymap(lambda key: calls.append(key) or key.lower(), {'A': 2, 'a': 3}, collision='combine', combine=lambda left, right: left + right) == {'a': 5}
    assert calls == ['A', 'a']


def test_factory_and_curried():
    "Verify factory and curried."
    from collections import OrderedDict
    from toolz.curried import keymap as curried
    result = curried(str.lower)({'A': 1, 'a': 2}, factory=OrderedDict, collision='first')
    assert isinstance(result, OrderedDict) and list(result.items()) == [('a', 1)]
