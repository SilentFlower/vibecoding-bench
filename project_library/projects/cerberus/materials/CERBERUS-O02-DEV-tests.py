"""finite约束是显式数值域政策，保留默认number行为。"""
from decimal import Decimal
from cerberus import Validator, TypeDefinition

def test_finite_float_matrix():
    """NaN与双向Infinity拒绝，普通值可用。@return None。"""
    validator = Validator({'value': {'type': 'number', 'finite': True}})
    assert validator.validate({'value': 0})
    for value in (float('nan'), float('inf'), -float('inf')):
        assert not validator.validate({'value': value})

def test_decimal_custom_type():
    """Decimal不经float降精度或范围转换。@return None。"""
    class DecimalValidator(Validator):
        types_mapping = Validator.types_mapping.copy()
        types_mapping['decimal'] = TypeDefinition('decimal', (Decimal,), ())
    validator = DecimalValidator({'value': {'type': 'decimal', 'finite': True}})
    assert validator.validate({'value': Decimal('1e9999')})
    assert not validator.validate({'value': Decimal('NaN')})

def test_disabled_and_schema_validation():
    """未启用finite的原行为保持，规则参数严格为bool。@return None。"""
    import pytest
    from cerberus import SchemaError
    assert Validator({'value': {'type': 'number'}}).validate({'value': float('nan')})
    assert Validator({'value': {'finite': False}}).validate({'value': float('inf')})
    with pytest.raises(SchemaError): Validator({'value': {'finite': 'yes'}})
