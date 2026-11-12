"Public regression tests for CERBERUS-O05-DEV; the complete business contract is in materials/CERBERUS-O05-DEV-contract.md."
from dataclasses import FrozenInstanceError
import pytest
from cerberus import Validator

def test_result_survives_next_call():
    "Verify result survives next call."
    validator = Validator({'count': {'type': 'integer'}})
    first = validator.validate_result({'count': 'bad'})
    second = validator.validate_result({'count': 4})
    assert not first.valid and first.errors and second.valid and second.errors == {}
    assert first.document == {'count': 'bad'} and first.completed

def test_deep_snapshot_and_frozen_shell():
    "Verify deep snapshot and frozen shell."
    validator = Validator({'rows': {'type': 'list'}})
    result = validator.validate_result({'rows': [{'x': 1}]})
    result.document['rows'][0]['x'] = 9
    assert validator.document['rows'][0]['x'] == 1
    with pytest.raises(FrozenInstanceError): result.valid = False

def test_normalization_and_update_options():
    "Verify normalization and update options."
    validator = Validator({'count': {'coerce': int}, 'required': {'required': True}})
    result = validator.validate_result({'count': '3'}, update=True)
    assert result.valid and result.document == {'count': 3}
