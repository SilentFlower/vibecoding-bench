"""选择结果保留双向类型、原顺序并独立于源表。"""
from bidict import bidict, OrderedBidict, frozenbidict

def test_keys_values_and_order():
    """键值条件组合，不按请求顺序打乱原表。@return None。"""
    from bidict.select import select
    source = OrderedBidict([('a', 1), ('b', 2), ('c', 3)])
    result = select(source, keys=['c', 'a'], values=[1, 3])
    assert list(result.items()) == [('a', 1), ('c', 3)] and result.inverse[3] == 'c'
    source['d'] = 4
    assert 'd' not in result

def test_empty_none_and_predicate():
    """空请求与None键语义明确，谓词实际生效。@return None。"""
    from bidict.select import select
    source = bidict({None: 0, 'a': 1})
    assert select(source, keys=[]) == {}
    assert select(source, predicate=lambda key, value: value == 0) == {None: 0}

def test_strict_and_frozen():
    """严格缺失与冻结结果类型。@return None。"""
    import pytest
    from bidict.select import select
    with pytest.raises(KeyError): select(bidict(a=1), values=[2], strict=True)
    assert isinstance(select(frozenbidict(a=1), keys=['a']), frozenbidict)
