"Public regression tests for CERBERUS-O04-DEV; the complete business contract is in materials/CERBERUS-O04-DEV-contract.md."
from cerberus import Validator

def test_missing_condition_true_and_false():
    "Verify missing condition true and false."
    validator = Validator({'kind': {}, 'value': {'required_if': {'field': 'kind', 'equals': 'choice'}}})
    assert not validator.validate({'kind': 'choice'})
    assert validator.validate({'kind': 'free'})
    assert validator.validate({'kind': 'choice', 'value': 0})

def test_defaults_and_update():
    "Verify defaults and update."
    schema = {'kind': {'default': 'choice'}, 'value': {'required_if': {'field': 'kind', 'equals': 'choice'}}}
    assert not Validator(schema).validate({})
    assert Validator(schema).validate({}, update=True)
    schema['value']['default'] = 7
    assert Validator(schema).validate({})

def test_root_false_and_nullable():
    "Verify root false and nullable."
    validator = Validator({'enabled': {}, 'child': {'type': 'dict', 'schema': {'value': {'nullable': True, 'required_if': {'field': '^enabled', 'equals': False}}}}})
    assert not validator.validate({'enabled': False, 'child': {}})
    assert validator.validate({'enabled': False, 'child': {'value': None}})
