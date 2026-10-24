"""重命名配置键保持顺序、子对象和安全属性映射。"""
import pytest
from box import Box, BoxError


def test_order_and_identity():
    """原位置改名且不重新转换子Box。@return None。"""
    value = Box({'before': 1, 'old name': {'port': 3}, 'after': 2})
    child = value['old name']
    assert value.rename_key('old name', 'new name') is value
    assert list(value) == ['before', 'new name', 'after']
    assert value.new_name is child
    with pytest.raises(KeyError):
        value['old name']


def test_collision_atomic():
    """冲突或保留键失败时原对象完全不动。@return None。"""
    value = Box({'a': 1, 'b c': 2})
    before = value.to_dict()
    for target in ['b c', 'b-c', 'to_dict']:
        with pytest.raises(BoxError):
            value.rename_key('a', target)
        assert value.to_dict() == before and list(value) == ['a', 'b c']


def test_integer_and_frozen():
    """整数键可改名，冻结对象拒绝。@return None。"""
    value = Box({2: 'value'})
    value.rename_key(2, 4)
    assert value[4] == 'value'
    with pytest.raises(BoxError):
        Box({'a': 1}, frozen_box=True).rename_key('a', 'b')
