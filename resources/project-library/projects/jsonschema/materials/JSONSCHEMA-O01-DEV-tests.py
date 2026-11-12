"Public regression tests for JSONSCHEMA-O01-DEV; the complete business contract is in materials/JSONSCHEMA-O01-DEV-contract.md."
from jsonschema import Draft201909Validator,Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

def test_true_items_with_unevaluated_false_accepts_entire_array():
    "Verify true items with unevaluated false accepts entire array."
    validator=Draft201909Validator({'items':True,'unevaluatedItems':False})
    for value in [[],[1],['a',{},None]]:assert list(validator.iter_errors(value))==[]

def test_false_items_produces_validation_error_not_typeerror():
    "Verify false items produces validation error not typeerror."
    validator=Draft201909Validator({'items':False,'unevaluatedItems':False})
    assert validator.is_valid([])
    errors=list(validator.iter_errors([1,2]));assert errors and all(isinstance(error,ValidationError) for error in errors)
    assert any('items' in error.schema_path for error in errors)

def test_tuple_additional_and_successful_composition_keep_draft_semantics():
    "Verify tuple additional and successful composition keep draft semantics."
    tuple_=Draft201909Validator({'items':[{'type':'integer'}],'unevaluatedItems':False})
    assert tuple_.is_valid([1]) and not tuple_.is_valid([1,2])
    combined=Draft201909Validator({'anyOf':[{'items':True},{'type':'string'}],'unevaluatedItems':False})
    assert combined.is_valid([1,2])
    assert Draft202012Validator({'prefixItems':[True],'unevaluatedItems':False}).is_valid([1])
