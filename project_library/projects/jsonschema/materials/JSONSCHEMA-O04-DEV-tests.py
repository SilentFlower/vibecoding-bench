"Public regression tests for JSONSCHEMA-O04-DEV; the complete business contract is in materials/JSONSCHEMA-O04-DEV-contract.md."
from jsonschema import FormatChecker,Draft202012Validator
from jsonschema.exceptions import FormatError,ValidationError
import re
import pytest

def test_conflicting_flags_and_deep_patterns_become_format_errors():
    "Verify conflicting flags and deep patterns become format errors."
    checker=FormatChecker()
    for pattern,cause in [('(?a)(?u)',ValueError),('('*1200+')'*1200,RecursionError),('[',re.error)]:
        with pytest.raises(FormatError) as caught:checker.check(pattern,'regex')
        assert isinstance(caught.value.cause,cause)

def test_actual_validator_reports_standard_validation_error_and_valid_controls():
    "Verify actual validator reports standard validation error and valid controls."
    validator=Draft202012Validator({'format':'regex'},format_checker=FormatChecker())
    errors=list(validator.iter_errors('(?a)(?u)'));assert len(errors)==1 and isinstance(errors[0],ValidationError)
    assert isinstance(errors[0].cause,ValueError)
    for value in ['',r'^[a-z]+$',42,b'[']:assert validator.is_valid(value)

def test_custom_checker_programming_errors_and_keyboard_interrupt_are_not_swallowed():
    "Verify custom checker programming errors and keyboard interrupt are not swallowed."
    checker=FormatChecker()
    @checker.checks('custom')
    def custom(value):raise ValueError('programming error')
    with pytest.raises(ValueError):checker.check('x','custom')
    @checker.checks('cancel')
    def cancel(value):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):checker.check('x','cancel')
