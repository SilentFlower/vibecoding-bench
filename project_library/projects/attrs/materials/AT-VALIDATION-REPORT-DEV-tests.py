"Public regression tests for AT-VALIDATION-REPORT-DEV; the complete business contract is in materials/AT-VALIDATION-REPORT-DEV-contract.md."
import attrs
import pytest
from attrs.validation import validate_all, MultiValidationError

def invalid_model():
    @attrs.define
    class Model:
        name: str = attrs.field(validator=attrs.validators.min_len(2))
        amount: int = attrs.field(validator=attrs.validators.ge(0))
    with attrs.validators.disabled():
        return Model('', -2)

def test_independent_errors_are_reported_in_declaration_order():
    model = invalid_model()
    issues = validate_all(model)
    assert [issue.field_name for issue in issues] == ['name','amount']
    assert issues[0].attribute is attrs.fields(type(model)).name

def test_aggregate_mode_retains_original_exception_objects():
    with pytest.raises(MultiValidationError) as failure:
        validate_all(invalid_model(), raise_errors=True)
    assert len(failure.value.issues) == 2 and isinstance(failure.value.issues[0].error, ValueError)

def test_global_disable_policy_and_valid_models_are_preserved():
    model = invalid_model()
    with attrs.validators.disabled():
        assert validate_all(model) == ()
    model = attrs.evolve(model, name='ok', amount=3)
    assert validate_all(model) == ()

def test_validator_is_called_once_and_values_are_not_changed():
    calls = []
    def check(instance, attribute, value):
        calls.append(value)
        raise LookupError('original')
    @attrs.define
    class Model:
        value: int = attrs.field(validator=check)
    with attrs.validators.disabled():
        model = Model(4)
    issues = validate_all(model)
    assert calls == [4] and model.value == 4 and isinstance(issues[0].error, LookupError)

def test_base_exceptions_are_not_swallowed():
    def stop(instance, attribute, value):
        raise KeyboardInterrupt()
    @attrs.define
    class Model:
        value = attrs.field(validator=stop)
    with attrs.validators.disabled():
        model = Model(1)
    with pytest.raises(KeyboardInterrupt):
        validate_all(model)

def test_regular_validation_still_fails_at_the_first_field():
    with pytest.raises(ValueError):
        attrs.validate(invalid_model())
