"Public regression tests for BIDICT-O03-DEV; the complete business contract is in materials/BIDICT-O03-DEV-contract.md."
from bidict import bidict, frozenbidict

def test_both_sides_and_inverse():
    "Verify both sides and inverse."
    from bidict.transform import transform_items
    source = bidict({1: 'A', 2: 'B'})
    output = transform_items(source, key_fn=str, value_fn=str.lower)
    assert output == {'1': 'a', '2': 'b'} and output.inverse['b'] == '2'
    assert source == {1: 'A', 2: 'B'}

def test_collision_rejected():
    "Verify collision rejected."
    import pytest
    from bidict.transform import transform_items
    with pytest.raises(ValueError): transform_items(bidict(a=1, A=2), key_fn=str.lower)
    with pytest.raises(ValueError): transform_items(bidict(a=1, b=2), value_fn=lambda value: 0)

def test_once_and_frozen():
    "Verify once and frozen."
    from bidict.transform import transform_items
    calls = []
    output = transform_items(frozenbidict(a=1), key_fn=lambda key: calls.append(key) or key)
    assert calls == ['a'] and isinstance(output, frozenbidict)
