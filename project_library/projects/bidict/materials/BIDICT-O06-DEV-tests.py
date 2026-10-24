"Public regression tests for BIDICT-O06-DEV; the complete business contract is in materials/BIDICT-O06-DEV-contract.md."
from bidict import bidict, OrderedBidict

def test_live_pair_identity():
    "Verify live pair identity."
    from bidict.readonly import ReadOnlyBidictProxy
    source = bidict(a=1)
    proxy = ReadOnlyBidictProxy(source)
    source['b'] = 2
    assert proxy['b'] == 2 and proxy.inverse[2] == 'b'
    assert proxy.inverse.inverse is proxy and proxy.inv is proxy.inverse

def test_write_rejected_both_sides():
    "Verify write rejected both sides."
    import pytest
    from bidict.readonly import ReadOnlyBidictProxy
    proxy = ReadOnlyBidictProxy(bidict(a=1))
    with pytest.raises(TypeError): proxy['a'] = 2
    with pytest.raises(TypeError): proxy.inverse[1] = 'b'
    with pytest.raises(TypeError): del proxy['a']

def test_views_clear_and_snapshot():
    "Verify views clear and snapshot."
    from bidict.readonly import ReadOnlyBidictProxy
    source = OrderedBidict([('b', 2), ('a', 1)])
    proxy = ReadOnlyBidictProxy(source)
    keys = proxy.keys()
    snapshot = proxy.copy()
    assert list(proxy) == ['b', 'a']
    source.clear()
    assert len(keys) == 0 and len(proxy.inverse) == 0 and snapshot == {'b': 2, 'a': 1}
