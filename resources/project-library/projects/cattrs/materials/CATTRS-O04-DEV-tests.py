"Public regression tests for CATTRS-O04-DEV; the complete business contract is in materials/CATTRS-O04-DEV-contract.md."
from dataclasses import dataclass
import pytest
from cattrs import Converter

def test_exact_primitives():
    "Verify exact primitives."
    from cattrs.strategies.strict import configure_strict_primitives
    converter = configure_strict_primitives(Converter())
    for value in ('2', True):
        with pytest.raises(TypeError): converter.structure(value, int)
    assert converter.structure(2, int) == 2 and converter.structure(False, bool) is False
    assert Converter().structure('2', int) == 2

def test_nested_path_and_float_policy():
    "Verify nested path and float policy."
    from cattrs.strategies.strict import configure_strict_primitives
    from cattrs.v import transform_error
    @dataclass
    class Record:
        "Public regression fixture: Record."
        quantity: int
    converter = configure_strict_primitives(Converter())
    with pytest.raises(Exception) as result: converter.structure({'quantity': '3'}, Record)
    assert 'quantity' in str(transform_error(result.value))
    assert configure_strict_primitives(Converter(), allow_int_float=True).structure(3, float) == 3.0

def test_nonfinite_and_subclass():
    "Verify nonfinite and subclass."
    from cattrs.strategies.strict import configure_strict_primitives
    converter = configure_strict_primitives(Converter())
    with pytest.raises(ValueError): converter.structure(float('nan'), float)
    class Text(str):
        "Public regression fixture: Text."
    with pytest.raises(TypeError): converter.structure(Text('x'), str)
