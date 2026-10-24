"Public regression tests for BIDICT-O01-DEV; the complete business contract is in materials/BIDICT-O01-DEV-contract.md."
from bidict import bidict, OrderedBidict, frozenbidict

def test_forward_inverse_composition():
    "Verify forward inverse composition."
    from bidict.compose import compose
    left, right = bidict(a=1, b=2), bidict({1: 'x', 2: 'y'})
    result = compose(left, right)
    assert result == {'a': 'x', 'b': 'y'}
    assert result.inverse == compose(right.inverse, left.inverse)
    assert left == {'a': 1, 'b': 2}

def test_missing_policies():
    "Verify missing policies."
    import pytest
    from bidict.compose import compose
    with pytest.raises(KeyError): compose(bidict(a=1), bidict())
    assert compose(bidict(a=1), bidict(), missing='ignore') == {}

def test_types_and_order():
    "Verify types and order."
    from bidict.compose import compose
    result = compose(OrderedBidict([('b', 2), ('a', 1)]), bidict({1: 'x', 2: 'y'}))
    assert isinstance(result, OrderedBidict) and list(result) == ['b', 'a']
    assert isinstance(compose(frozenbidict(a=1), bidict({1: 2})), frozenbidict)
