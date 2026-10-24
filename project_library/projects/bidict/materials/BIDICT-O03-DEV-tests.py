"""真实键值转换的最终唯一性须显式校验。"""
from bidict import bidict, frozenbidict

def test_both_sides_and_inverse():
    """两侧转换后类型和值真实改变且可反查。@return None。"""
    from bidict.transform import transform_items
    source = bidict({1: 'A', 2: 'B'})
    output = transform_items(source, key_fn=str, value_fn=str.lower)
    assert output == {'1': 'a', '2': 'b'} and output.inverse['b'] == '2'
    assert source == {1: 'A', 2: 'B'}

def test_collision_rejected():
    """转换后重复键或值拒绝，不能静默丢行。@return None。"""
    import pytest
    from bidict.transform import transform_items
    with pytest.raises(ValueError): transform_items(bidict(a=1, A=2), key_fn=str.lower)
    with pytest.raises(ValueError): transform_items(bidict(a=1, b=2), value_fn=lambda value: 0)

def test_once_and_frozen():
    """每个键值一次，冻结输入保持结果类型。@return None。"""
    from bidict.transform import transform_items
    calls = []
    output = transform_items(frozenbidict(a=1), key_fn=lambda key: calls.append(key) or key)
    assert calls == ['a'] and isinstance(output, frozenbidict)
