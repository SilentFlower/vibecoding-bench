"Public regression tests for AP-FORMAT-DEV; the complete business contract is in materials/AP-FORMAT-DEV-contract.md."
from alive_progress.core.configuration import _format_input_factory,ERROR

def test_unknown_nested_fields_are_rejected():
    validate=_format_input_factory('count total')
    assert validate('{count:{missing}}') is ERROR

def test_valid_nested_width_and_escaped_braces_are_preserved():
    validate=_format_input_factory('count total')
    assert validate('{count!s:>{total}}')=='{count!s:>{total}}'
    assert validate('{{literal}} {count}')=='{{literal}} {count}'

def test_bad_conversions_traversal_and_braces_are_rejected():
    validate=_format_input_factory('count total')
    for text in ('{count!q}','{count.attr}','{count[0]}','{count','{count:{total:{count}}}'):
        assert validate(text) is ERROR

def test_legacy_plain_and_boolean_inputs_keep_existing_behavior():
    validate=_format_input_factory('count')
    assert validate('plain')=='plain' and validate(False) is False and validate(True) is True
