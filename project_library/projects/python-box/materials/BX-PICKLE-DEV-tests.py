"""pickle往返后保持Box子类及嵌套列表里的真实类型。"""
import pickle
from box import Box


class ConfigSubclass(Box):
    """实际业务配置子类。"""


def test_nested_subclasses_roundtrip():
    """直接子节点和列表子节点都保持子类。@return None。"""
    original = ConfigSubclass({'child': {'port': 9}, 'rows': [{'port': 10}]})
    for protocol in range(2, pickle.HIGHEST_PROTOCOL + 1):
        result = pickle.loads(pickle.dumps(original, protocol=protocol))
        assert type(result) is ConfigSubclass
        assert type(result.child) is ConfigSubclass
        assert type(result.rows[0]) is ConfigSubclass
        assert result == original


def test_frozen_options_and_plain_box():
    """冻结和默认节点选项不丢失，普通Box继续正常。@return None。"""
    original = ConfigSubclass({'child': {'port': 9}}, frozen_box=True, default_box=True)
    result = pickle.loads(pickle.dumps(original))
    assert type(result.child) is ConfigSubclass
    assert result._box_config['frozen_box'] is True
    assert result._box_config['default_box'] is True
    assert pickle.loads(pickle.dumps(Box({'port': 9}))).port == 9


def test_existing_shared_nodes():
    """已经存在的共享引用不应在恢复时被重新转换拆开。@return None。"""
    original = ConfigSubclass({'child': {'port': 9}})
    dict.__setitem__(original, 'alias', original.child)
    result = pickle.loads(pickle.dumps(original))
    assert result.alias is result.child
