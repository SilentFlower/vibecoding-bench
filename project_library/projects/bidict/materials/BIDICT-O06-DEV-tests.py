"""只读代理与既有冻结快照不同，必须保持实时双向关联。"""
from bidict import bidict, OrderedBidict

def test_live_pair_identity():
    """源更新后两个方向均可读且inverse身份稳定。@return None。"""
    from bidict.readonly import ReadOnlyBidictProxy
    source = bidict(a=1)
    proxy = ReadOnlyBidictProxy(source)
    source['b'] = 2
    assert proxy['b'] == 2 and proxy.inverse[2] == 'b'
    assert proxy.inverse.inverse is proxy and proxy.inv is proxy.inverse

def test_write_rejected_both_sides():
    """代理和逆向代理都不允许赋值删除。@return None。"""
    import pytest
    from bidict.readonly import ReadOnlyBidictProxy
    proxy = ReadOnlyBidictProxy(bidict(a=1))
    with pytest.raises(TypeError): proxy['a'] = 2
    with pytest.raises(TypeError): proxy.inverse[1] = 'b'
    with pytest.raises(TypeError): del proxy['a']

def test_views_clear_and_snapshot():
    """普通视图不泄漏写入，独立快照不随源clear。@return None。"""
    from bidict.readonly import ReadOnlyBidictProxy
    source = OrderedBidict([('b', 2), ('a', 1)])
    proxy = ReadOnlyBidictProxy(source)
    keys = proxy.keys()
    snapshot = proxy.copy()
    assert list(proxy) == ['b', 'a']
    source.clear()
    assert len(keys) == 0 and len(proxy.inverse) == 0 and snapshot == {'b': 2, 'a': 1}
