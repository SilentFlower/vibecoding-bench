"""公开数字星期回归。"""
import pytest
import arrow
from arrow.parser import DateTimeParser, ParserError

def test_all_iso_weekdays_roundtrip():
    for value in range(1, 8):
        assert arrow.get(str(value), 'd').format('d') == str(value)

def test_numeric_and_named_weekdays_use_the_same_anchor():
    assert arrow.get('3', 'd') == arrow.get('Wednesday', 'dddd')

def test_year_and_month_context_is_preserved():
    result = arrow.get('2024-02 7', 'YYYY-MM d')
    assert (result.year, result.month, result.day, result.isoweekday()) == (2024, 2, 4, 7)

def test_complete_date_keeps_existing_named_weekday_precedence():
    assert arrow.get('2024-05-06 7', 'YYYY-MM-DD d').day == 6

def test_invalid_numeric_weekdays_are_rejected():
    for value in ('0', '8', '03'):
        with pytest.raises(ParserError):
            DateTimeParser().parse(value, 'd')

def test_named_weekdays_and_other_date_tokens_are_unchanged():
    assert arrow.get('Monday', 'dddd').format('d') == '1'
    assert arrow.get('2024-06-18', 'YYYY-MM-DD').day == 18
