"Public regression tests for JSONSCHEMA-O06-DEV; the complete business contract is in materials/JSONSCHEMA-O06-DEV-contract.md."
from jsonschema import FormatChecker,Draft202012Validator
from jsonschema.exceptions import FormatError
import pytest

def test_builtin_date_and_business_year_shortcircuit_without_global_change():
    "Verify builtin date and business year shortcircuit without global change."
    checker=FormatChecker();other=FormatChecker();calls=[]
    checker.compose('date',lambda value:calls.append(value) or value.startswith('2026-'),mode='all')
    assert checker.conforms('2026-02-01','date') and not checker.conforms('2025-02-01','date')
    assert not checker.conforms('not-a-date','date') and calls==['2026-02-01','2025-02-01']
    assert other.conforms('2025-02-01','date')
    validator=Draft202012Validator({'format':'date'},format_checker=checker);assert not validator.is_valid('2025-02-01')

def test_any_shortcircuit_declared_errors_and_original_causes():
    "Verify any shortcircuit declared errors and original causes."
    checker=FormatChecker();calls=[]
    checker.compose('date',lambda value:calls.append(value) or value=='today',mode='any')
    assert checker.conforms('2026-02-01','date') and calls==[]
    assert checker.conforms('today','date') and calls==['today']
    other=FormatChecker()
    def domain(value):raise LookupError('domain rejected')
    other.compose('date',domain,raises=LookupError)
    with pytest.raises(FormatError) as caught:other.check('2026-01-01','date')
    assert isinstance(caught.value.cause,LookupError)

def test_invalid_compositions_and_programming_errors_keep_explicit_boundaries():
    "Verify invalid compositions and programming errors keep explicit boundaries."
    checker=FormatChecker()
    with pytest.raises(KeyError):checker.compose('unknown',lambda value:True)
    with pytest.raises(ValueError):checker.compose('date',lambda value:True,mode='maybe')
    with pytest.raises(TypeError):checker.compose('date',None)
    def broken(value):raise RuntimeError('programming error')
    checker.compose('date',broken)
    with pytest.raises(RuntimeError):checker.check('2026-01-01','date')
