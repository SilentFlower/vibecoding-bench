"""嵌套删除仅复制修改路径并支持严格和清理政策。"""
from collections import OrderedDict
import pytest
from toolz import dissoc_in
from toolz.curried import dissoc_in as curried


def test_delete_and_share_untouched():
    """叶子删除保持兄弟和未修改分支引用。@return None。"""
    original = {'account': {'secret': 1, 'name': 'x'}, 'other': {'value': 2}}
    result = dissoc_in(original, ['account', 'secret'])
    assert result == {'account': {'name': 'x'}, 'other': {'value': 2}}
    assert original['account']['secret'] == 1
    assert result['other'] is original['other']
    assert result['account'] is not original['account']


def test_missing_prune_and_factory():
    """缺失路径、父节点清理和映射工厂均显式。@return None。"""
    assert dissoc_in({'a': {'b': 1}}, ['a', 'b']) == {'a': {}}
    assert dissoc_in({'a': {'b': 1}}, ['a', 'b'], prune=True) == {}
    with pytest.raises(KeyError):
        dissoc_in({}, ['a'], strict=True)
    assert isinstance(dissoc_in({'a': 1}, ['a'], factory=OrderedDict), OrderedDict)


def test_curried_and_invalid_paths():
    """导出可组合，空路径和标量祖先不静默处理。@return None。"""
    assert curried({'a': 1})(['a']) == {}
    with pytest.raises(ValueError):
        dissoc_in({}, [])
    with pytest.raises(TypeError):
        dissoc_in({'a': 1}, ['a', 'b'])
