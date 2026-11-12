"Public regression tests for CH-JSON-PRECISION-DEV; the complete business contract is in materials/CH-JSON-PRECISION-DEV-contract.md."
from decimal import Decimal
import json
import pytest
from cli_helpers.tabular_output.json_output_adapter import adapter

def test_decimal_string_policy_preserves_precision_and_scale():
    value=Decimal('12345678901234567890.1200')
    assert json.loads(next(adapter([[value]],['amount'],decimal_policy='string')))['amount']==str(value)

def test_nested_decimal_is_exact_and_large_integer_stays_numeric():
    value={'nested':[Decimal('0.00100')],'count':10**30}
    result=json.loads(next(adapter([[value]],['data'],decimal_policy='string')))
    assert result=={'data':{'nested':['0.00100'],'count':10**30}}

def test_strict_json_rejects_nonfinite_float_and_decimal_in_all_policies():
    for value in (float('nan'),float('inf'),Decimal('NaN'),{'x':Decimal('Infinity')}):
        for policy in ('float','string'):
            with pytest.raises(ValueError):
                next(adapter([[value]],['a'],strict_json=True,decimal_policy=policy))

def test_old_default_and_later_calls_do_not_inherit_policy():
    value=Decimal('1.20')
    assert json.loads(next(adapter([[value]],['a'],decimal_policy='string')))['a']=='1.20'
    assert json.loads(next(adapter([[value]],['a'])))['a']==1.2
