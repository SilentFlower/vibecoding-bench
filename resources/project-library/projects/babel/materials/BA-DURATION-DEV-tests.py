"Public regression tests for BA-DURATION-DEV; the complete business contract is in materials/BA-DURATION-DEV-contract.md."
from datetime import timedelta
import pytest
from babel.dates import format_duration
from babel.units import format_unit
from babel.lists import format_list

def test_multiple_components_use_locale_unit_lists():
    expected = format_list([format_unit(1,'duration-hour',locale='en'), format_unit(2,'duration-minute',locale='en'), format_unit(3,'duration-second',locale='en')], style='unit', locale='en')
    assert format_duration(3723, locale='en') == expected

def test_fractional_smallest_unit_and_timedelta_are_preserved():
    assert format_duration(timedelta(seconds=1, microseconds=500000), locale='en') == format_unit(1.5,'duration-second',locale='en')

def test_zero_and_maximum_components_have_defined_behavior():
    assert format_duration(0, units=('hour','minute'), locale='fr') == format_unit(0,'duration-minute',locale='fr')
    assert format_duration(3723, max_parts=1, locale='en') == format_unit(1,'duration-hour',locale='en')

def test_invalid_values_and_calendar_units_are_rejected():
    for options in ({'units':('second','hour')}, {'units':('month',)}, {'units':()}, {'max_parts':0}):
        with pytest.raises(ValueError):
            format_duration(2, locale='en', **options)
    with pytest.raises(ValueError):
        format_duration(-1, locale='en')
