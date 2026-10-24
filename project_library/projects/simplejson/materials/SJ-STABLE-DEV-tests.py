"""公开稳定JSON编码回归。"""
from decimal import Decimal
import pytest
from simplejson.stable import stable_dumps,stable_bytes

def test_nested_mapping_order_and_utf8_bytes_are_stable():
    value={'中':1,'a':{'z':2,'a':'é'}}
    assert stable_dumps(value)=='{"a":{"a":"é","z":2},"中":1}'
    assert stable_bytes(value)==stable_dumps(value).encode('utf-8')

def test_decimal_precision_and_false_are_preserved():
    assert stable_dumps({'v':Decimal('1.2300'),'b':False})=='{"b":false,"v":1.2300}'

def test_nonfinite_and_nonstring_keys_fail_at_any_depth():
    for value in ({'x':float('nan')},{'x':Decimal('Infinity')},{'x':{1:'a'}}):
        with pytest.raises((ValueError,TypeError)): stable_dumps(value)

def test_cycles_surrogates_and_nonjson_containers_are_rejected():
    value=[];value.append(value)
    with pytest.raises(ValueError): stable_dumps(value)
    with pytest.raises(UnicodeEncodeError): stable_dumps('\ud800')
    with pytest.raises(TypeError): stable_dumps((1,2))
