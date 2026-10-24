"""显式分段路径区分字面点键、整数键和列表索引。"""
import pytest
from box import Box, BoxError


def test_literal_segments():
    """整数键和字符串键及含点键保持区别。@return None。"""
    value = Box({'a.b': {'2': 'text', 2: 'integer'}, 'rows': [{'n': 1}]})
    assert value.get_path(['a.b', 2]) == 'integer'
    assert value.get_path(['a.b', '2']) == 'text'
    assert value.get_path(['rows', -1, 'n']) == 1


def test_assignment_and_delete():
    """仅已存在父结构内写删，字面点不解析。@return None。"""
    value = Box({'node': {}}, box_dots=True, default_box=True)
    value.set_path(['node', 'a.b'], {'x': 2})
    assert value.get_path(['node', 'a.b', 'x']) == 2
    value.delete_path(['node', 'a.b'])
    assert value.get_path(['node', 'a.b'], None) is None


def test_missing_no_default_creation_and_frozen():
    """读取不创建默认节点，冻结写入拒绝。@return None。"""
    value = Box(default_box=True)
    assert value.get_path(['missing'], None) is None and value.to_dict() == {}
    with pytest.raises(ValueError):
        value.get_path([])
    with pytest.raises(BoxError):
        Box({'a': 1}, frozen_box=True).set_path(['a'], 2)
