"Public regression tests for AR-STRICT-DEV; the complete business contract is in materials/AR-STRICT-DEV-contract.md."
from datetime import datetime
import pytest
import arrow
from arrow.parser import DateTimeParser, ParserError

def test_strict_rejects_prefix_and_suffix_but_default_keeps_extraction():
    text = 'prefix 2024-05-06 suffix'
    assert arrow.get(text, 'YYYY-MM-DD').day == 6
    with pytest.raises(ParserError):
        arrow.get(text, 'YYYY-MM-DD', strict=True)

def test_explicit_parser_and_factory_accept_complete_valid_input():
    assert DateTimeParser().parse_strict('2024-05-06', 'YYYY-MM-DD') == datetime(2024,5,6)
    assert arrow.get('2024-05-06', 'YYYY-MM-DD', strict=True).year == 2024

def test_single_numeric_tokens_can_require_exact_width():
    parser = DateTimeParser()
    assert parser.parse_strict('2024-12-6', 'YYYY-M-D').month == 12
    with pytest.raises(ParserError):
        parser.parse_strict('2024-12-6', 'YYYY-M-D', exact_width=True)

def test_fractional_width_and_literal_text_are_distinguished():
    parser = DateTimeParser()
    assert parser.parse_strict('at 05:06:07.123', '[at] HH:mm:ss.SSS', exact_width=True).microsecond == 123000
    with pytest.raises(ParserError):
        parser.parse_strict('05:06:07.12', 'HH:mm:ss.SSS', exact_width=True)

def test_format_list_calendar_and_whitespace_validation():
    assert DateTimeParser().parse_strict('2024-05-06', ['YYYY/MM/DD','YYYY-MM-DD']).day == 6
    assert DateTimeParser().parse_strict('2024-05-06	12:30', 'YYYY-MM-DD HH:mm', True).hour == 12
    with pytest.raises(ParserError):
        DateTimeParser().parse_strict('2024-02-30', 'YYYY-MM-DD')

def test_numeric_weekday_and_invalid_options():
    assert arrow.get('3', 'd', strict=True).isoweekday() == 3
    with pytest.raises(ValueError):
        arrow.get('2024-05-06', 'YYYY-MM-DD', exact_width=True)
    with pytest.raises(TypeError):
        arrow.get('2024-05-06', strict=True)
