"Public regression tests for BA-PREFERENCES-DEV; the complete business contract is in materials/BA-PREFERENCES-DEV-contract.md."
import pytest
from babel.core import negotiate_locale_preferences

def test_quality_and_available_spelling_are_preserved():
    assert negotiate_locale_preferences('en-US;q=0.5, de-DE;q=0.9', ['en_US','de_DE']) == 'de_DE'
    assert negotiate_locale_preferences('de-de', ['de_de']) == 'de_de'

def test_ties_and_iterable_available_are_stable():
    assert negotiate_locale_preferences('fr, de', iter(['de','fr'])) == 'fr'

def test_zero_quality_excludes_language_from_wildcard():
    assert negotiate_locale_preferences('en;q=0, *;q=0.5', ['en_US','fr']) == 'fr'
    assert negotiate_locale_preferences('*;q=0', ['fr']) is None

def test_aliases_and_invalid_headers_have_explicit_behavior():
    assert negotiate_locale_preferences('no', ['nb_NO']) == 'nb_NO'
    for value in ('en;q=1.1', 'en;q=0.1234', 'en;bad=1', 'en,' * 100):
        with pytest.raises(ValueError):
            negotiate_locale_preferences(value, ['en'])
