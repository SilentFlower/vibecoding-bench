"""仅更新模式不能创建缺失路径或触发不必要回调。"""
import pytest
from toolz import update_in


def test_missing_never_calls_function():
    """缺失叶子或祖先均返回未修改副本。@return None。"""
    original = {'a': {'b': 1}}
    calls = []
    for path in (['a', 'missing'], ['missing', 'b']):
        result = update_in(original, path, lambda value: calls.append(value), create=False)
        assert result == original and result is not original
    assert calls == []


def test_none_is_existing_and_curried():
    """None是存在值，curried入口继承策略。@return None。"""
    from toolz.curried import update_in as curried
    assert update_in({'a': None}, ['a'], lambda value: value is None, create=False) == {'a': True}
    assert curried({'a': 1}, ['a'])(lambda value: value + 1, create=False) == {'a': 2}


def test_default_upsert_and_error():
    """默认创建语义不变，空的仅更新路径拒绝。@return None。"""
    assert update_in({}, ['a', 'b'], lambda value: value + 1, default=0) == {'a': {'b': 1}}
    with pytest.raises(ValueError):
        update_in({}, [], lambda value: value, create=False)
