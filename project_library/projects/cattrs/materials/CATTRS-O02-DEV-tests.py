"Public regression tests for CATTRS-O02-DEV; the complete business contract is in materials/CATTRS-O02-DEV-contract.md."
from dataclasses import dataclass
from decimal import Decimal
import pytest
from cattrs.preconf.json import make_converter

def test_precise_json_roundtrip():
    "Verify precise json roundtrip."
    from cattrs.strategies.decimal import configure_decimal
    @dataclass
    class Money:
        "Public regression fixture: Money."
        amount: Decimal
    converter = configure_decimal(make_converter())
    value = Money(Decimal('123456789.1234567890123456789'))
    assert converter.loads(converter.dumps(value), Money) == value
    assert converter.unstructure(Decimal('-0.00')) == '-0.00'

def test_invalid_and_special_policy():
    "Verify invalid and special policy."
    from cattrs.strategies.decimal import configure_decimal
    converter = configure_decimal(make_converter())
    for value in ['bad', 'NaN', 'Infinity']:
        with pytest.raises(ValueError): converter.structure(value, Decimal)
    with pytest.raises(TypeError): converter.structure(0.1, Decimal)
    assert configure_decimal(make_converter(), allow_special=True).structure('Infinity', Decimal).is_infinite()

def test_user_hook_after_configuration():
    "Verify user hook after configuration."
    from cattrs.strategies.decimal import configure_decimal
    converter = configure_decimal(make_converter())
    converter.register_unstructure_hook(Decimal, lambda value: 'custom')
    assert converter.unstructure(Decimal(1)) == 'custom'
