"Public regression tests for BA-RANGE-DEV; the complete business contract is in materials/BA-RANGE-DEV-contract.md."
from decimal import Decimal
import pytest
from babel import Locale
from babel.numbers import format_number_range, format_decimal, format_currency, UnknownCurrencyError

def test_decimal_endpoints_use_locale_pattern():
    locale = Locale.parse('de')
    expected = locale.interval_formats[None].replace('{0}', '1,2').replace('{1}', '3,4')
    assert format_number_range('1.2', '3.4', locale='de') == expected

def test_currency_and_options_preserve_both_complete_endpoints():
    text = format_number_range(-3, 4, currency='USD', locale='en', group_separator=False)
    assert format_currency(-3, 'USD', locale='en') in text and format_currency(4, 'USD', locale='en') in text

def test_rounded_equality_can_be_collapsed_or_shown():
    assert format_number_range('1.001', '1.002', locale='en', format='0.0') == '1.0'
    assert format_number_range('1.001', '1.002', locale='en', format='0.0', collapse=False).count('1.0') == 2

def test_invalid_ranges_and_currency_fail():
    for first, last in ((2, 1), ('NaN', 2), (0, 'Infinity')):
        with pytest.raises(ValueError):
            format_number_range(first, last, locale='en')
    with pytest.raises(UnknownCurrencyError):
        format_number_range(1, 2, currency='NOT', locale='en')
