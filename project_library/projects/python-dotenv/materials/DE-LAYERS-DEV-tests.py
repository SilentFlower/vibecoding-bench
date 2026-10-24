"Public regression tests for DE-LAYERS-DEV; the complete business contract is in materials/DE-LAYERS-DEV-contract.md."
import os
import pytest
from dotenv.layers import load_layers
from dotenv.validation import ConfigValidationError

def test_layers_and_origin_follow_last_definition():
    result = load_layers(iter([('base','A=one\nB=${A}\n'),('local','A=two\nC=${A}/${B}\n')]))
    assert dict(result.values) == {'A':'two','B':'one','C':'two/one'}
    assert result.origins['A'] == ('local',1) and result.origins['C'] == ('local',2)

def test_override_uses_only_explicit_environment():
    sources = [('base','A=config\nB=${A}\n')]
    assert load_layers(sources, environment={'A':'external'}, override=False).values['B'] == 'external'
    assert load_layers(sources, environment={'A':'external'}).values['B'] == 'config'

def test_disabled_interpolation_and_valueless_entries():
    result = load_layers([('base','A\nB=${UNKNOWN:-fallback}\n')], interpolate=False)
    assert result.values['A'] is None and result.values['B'] == '${UNKNOWN:-fallback}'

def test_duplicate_layers_and_invalid_late_input_fail_without_environment_changes():
    before = dict(os.environ)
    with pytest.raises(ValueError):
        load_layers([('x','A=1'),('x','A=2')])
    with pytest.raises(ConfigValidationError):
        load_layers([('x','A=1'),('bad','A="bad')])
    assert dict(os.environ) == before
