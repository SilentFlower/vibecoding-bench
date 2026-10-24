"""组合仍能反查，顺序和源对象保持。"""
from bidict import bidict, OrderedBidict, frozenbidict

def test_forward_inverse_composition():
    """正组合的inverse等于反向组合。@return None。"""
    from bidict.compose import compose
    left, right = bidict(a=1, b=2), bidict({1: 'x', 2: 'y'})
    result = compose(left, right)
    assert result == {'a': 'x', 'b': 'y'}
    assert result.inverse == compose(right.inverse, left.inverse)
    assert left == {'a': 1, 'b': 2}

def test_missing_policies():
    """严格缺项失败，交集策略保留匹配项。@return None。"""
    import pytest
    from bidict.compose import compose
    with pytest.raises(KeyError): compose(bidict(a=1), bidict())
    assert compose(bidict(a=1), bidict(), missing='ignore') == {}

def test_types_and_order():
    """有序和冻结结果保持各自类型。@return None。"""
    from bidict.compose import compose
    result = compose(OrderedBidict([('b', 2), ('a', 1)]), bidict({1: 'x', 2: 'y'}))
    assert isinstance(result, OrderedBidict) and list(result) == ['b', 'a']
    assert isinstance(compose(frozenbidict(a=1), bidict({1: 2})), frozenbidict)
