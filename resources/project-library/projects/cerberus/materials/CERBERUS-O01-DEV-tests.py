"Public regression tests for CERBERUS-O01-DEV; the complete business contract is in materials/CERBERUS-O01-DEV-contract.md."
from cerberus import Validator

def test_identity_keeps_value():
    "Verify identity keeps value."
    validator = Validator({'x': {'rename': 'x'}})
    assert validator.normalized({'x': 7}) == {'x': 7}

def test_combined_rename_then_handler():
    "Verify combined rename then handler."
    validator = Validator({'x': {'rename': 'target', 'rename_handler': str.upper}}, allow_unknown=True)
    assert validator.normalized({'x': 8}) == {'TARGET': 8}

def test_original_and_handler_failure():
    "Verify original and handler failure."
    source = {'x': [1]}
    def fail(name):
        "Support the public regression through fail."
        raise ValueError('name')
    validator = Validator({'x': {'rename': 'new', 'rename_handler': fail}}, allow_unknown=True)
    result = validator.normalized(source, always_return_document=True)
    assert source == {'x': [1]} and result == {'x': [1]} and validator.errors
