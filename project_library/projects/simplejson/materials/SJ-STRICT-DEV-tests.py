"""公开严格解码回归。"""
from decimal import Decimal
import pytest
import simplejson
from simplejson.strict import strict_loads

def test_duplicate_nested_and_escaped_keys_are_rejected():
    with pytest.raises(ValueError): strict_loads('{"v":{"a":1,"\\u0061":2}}')

def test_nonfinite_constants_and_float_overflow_are_rejected():
    for value in ('NaN','Infinity','-Infinity','1e999'):
        with pytest.raises(ValueError): strict_loads(value)

def test_decimal_mode_preserves_exact_value_and_normal_integers():
    result=strict_loads('{"price":1.2300,"n":12345678901234567890}',use_decimal=True)
    assert result['price']==Decimal('1.2300') and result['price'].as_tuple().exponent==-4
    assert type(result['n']) is int

def test_real_bytes_and_legacy_default_behavior_are_preserved():
    assert strict_loads(b'{"x":false}')=={'x':False}
    assert simplejson.loads('{"a":1,"a":2}')=={'a':2}
