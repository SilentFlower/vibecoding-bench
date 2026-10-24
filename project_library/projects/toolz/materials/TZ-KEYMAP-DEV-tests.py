"""键归一化冲突不能只能静默覆盖。"""
import pytest
from toolz import keymap


def test_collision_policies():
    """默认末项兼容，首项和严格政策显式生效。@return None。"""
    values = {'A': 1, 'a': 2}
    assert keymap(str.lower, values) == {'a': 2}
    assert keymap(str.lower, values, collision='first') == {'a': 1}
    with pytest.raises(ValueError):
        keymap(str.lower, values, collision='error')
    assert values == {'A': 1, 'a': 2}


def test_combiner_and_once():
    """转换每键一次，业务归并按顺序执行。@return None。"""
    calls = []
    assert keymap(lambda key: calls.append(key) or key.lower(), {'A': 2, 'a': 3}, collision='combine', combine=lambda left, right: left + right) == {'a': 5}
    assert calls == ['A', 'a']


def test_factory_and_curried():
    """工厂和curried入口保留。@return None。"""
    from collections import OrderedDict
    from toolz.curried import keymap as curried
    result = curried(str.lower)({'A': 1, 'a': 2}, factory=OrderedDict, collision='first')
    assert isinstance(result, OrderedDict) and list(result.items()) == [('a', 1)]
