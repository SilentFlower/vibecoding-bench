"Public regression tests for WRAPT-05-DEV; the complete business contract is in materials/WRAPT-05-DEV-contract.md."
import unittest
from wrapt.canonical_cache import canonical_cache

def test_equivalent_defaults_varargs_kwargs_and_typed_policy():
    "Verify equivalent defaults varargs kwargs and typed policy."
    calls=[]
    @canonical_cache(maxsize=3)
    def value(x,y=2,*,z=3):calls.append(1);return x+y+z
    assert value(1)==value(x=1)==value(1,y=2,z=3)==6 and calls==[1]
    @canonical_cache(typed=True)
    def typed(x):return type(x)
    assert typed(1) is int and typed(True) is bool and typed.cache_info().misses==2

def test_custom_business_key_supports_mapping_and_invalid_calls_still_reject():
    "Verify custom business key supports mapping and invalid calls still reject."
    calls=[]
    @canonical_cache(key_func=lambda bound:bound.arguments['record']['id'])
    def value(record):calls.append(1);return record['name']
    assert value({'id':7,'name':'first'})==value({'id':7,'name':'second'})=='first' and calls==[1]
    with unittest.TestCase().assertRaises(TypeError):value()
    @canonical_cache()
    def plain(record):return record
    with unittest.TestCase().assertRaises(TypeError):plain({})

