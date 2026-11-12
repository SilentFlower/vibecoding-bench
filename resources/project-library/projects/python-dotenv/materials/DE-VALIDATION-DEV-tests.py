"Public regression tests for DE-VALIDATION-DEV; the complete business contract is in materials/DE-VALIDATION-DEV-contract.md."
import pytest
from dotenv.validation import parse_config, ConfigValidationError

def test_values_and_original_multiline_locations():
    result = parse_config('A="one\ntwo"\nB=\nC\n')
    assert dict(result.values) == {'A':'one\ntwo','B':'','C':None}
    assert dict(result.lines) == {'A':1,'B':3,'C':4}

def test_errors_are_complete_and_do_not_leak_values():
    with pytest.raises(ConfigValidationError) as caught:
        parse_config('A=secret\nA=other\nBAD="unterminated\n', required=('MISSING',))
    assert [item[0] for item in caught.value.issues] == ['duplicate','syntax','required']
    assert 'secret' not in str(caught.value) and 'other' not in str(caught.value)

def test_last_definition_and_required_empty_are_explicit():
    result = parse_config('A=old\nA=\n', duplicates='last', required=('A',))
    assert result.values['A'] == '' and result.lines['A'] == 2

def test_result_is_read_only_and_valueless_required_is_rejected():
    result = parse_config('A=1\n')
    with pytest.raises(TypeError):
        result.values['A'] = '2'
    with pytest.raises(ConfigValidationError):
        parse_config('A\n', required=('A',))
