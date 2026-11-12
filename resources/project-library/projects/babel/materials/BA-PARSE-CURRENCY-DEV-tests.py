"Public regression tests for BA-PARSE-CURRENCY-DEV; the complete business contract is in materials/BA-PARSE-CURRENCY-DEV-contract.md."
from decimal import Decimal
import pytest
from babel.numbers import parse_currency, format_currency, NumberFormatError

def test_standard_amounts_round_trip_across_locales():
    for locale, currency in (('en_US', 'USD'), ('de_DE', 'EUR'), ('ja_JP', 'JPY')):
        for value in (Decimal('1234'), Decimal('-42')):
            assert parse_currency(format_currency(value, currency, locale=locale), currency, locale) == value

def test_accounting_negative_and_iso_code_are_supported():
    assert parse_currency('($42.00)', 'USD', 'en_US') == -42
    assert parse_currency('USD42.00', 'USD', 'en_US') == 42

def test_currency_and_full_input_are_required():
    for text in ('42.00', '€42.00', '$42.00junk', '$+42.00', '($42.00', '$NaN'):
        with pytest.raises(NumberFormatError):
            parse_currency(text, 'USD', 'en_US')

def test_strict_precision_and_relaxed_grouping_are_explicit():
    with pytest.raises(NumberFormatError):
        parse_currency('$4.2', 'USD', 'en_US')
    assert parse_currency('$4.2', 'USD', 'en_US', strict=False) == Decimal('4.2')
