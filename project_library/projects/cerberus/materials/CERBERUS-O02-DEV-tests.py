"Public regression tests for CERBERUS-O02-DEV; the complete business contract is in materials/CERBERUS-O02-DEV-contract.md."
from decimal import Decimal
from cerberus import Validator, TypeDefinition

def test_finite_float_matrix():
    "Verify finite float matrix."
    validator = Validator({'value': {'type': 'number', 'finite': True}})
    assert validator.validate({'value': 0})
    for value in (float('nan'), float('inf'), -float('inf')):
        assert not validator.validate({'value': value})

def test_decimal_custom_type():
    "Verify decimal custom type."
    class DecimalValidator(Validator):
        types_mapping = Validator.types_mapping.copy()
        types_mapping['decimal'] = TypeDefinition('decimal', (Decimal,), ())
    validator = DecimalValidator({'value': {'type': 'decimal', 'finite': True}})
    assert validator.validate({'value': Decimal('1e9999')})
    assert not validator.validate({'value': Decimal('NaN')})

def test_disabled_and_schema_validation():
    "Verify disabled and schema validation."
    import pytest
    from cerberus import SchemaError
    assert Validator({'value': {'type': 'number'}}).validate({'value': float('nan')})
    assert Validator({'value': {'finite': False}}).validate({'value': float('inf')})
    with pytest.raises(SchemaError): Validator({'value': {'finite': 'yes'}})
