"Public regression tests for HUMANIZE-O05-DEV; the complete business contract is in materials/HUMANIZE-O05-DEV-contract.md."
from datetime import date,datetime,timedelta,timezone
import humanize
import pytest

def test_month_end_leap_year_and_direct_anchor():
    "Verify month end leap year and direct anchor."
    from humanize.calendar import calendar_interval
    result=calendar_interval(date(2024,1,31),date(2024,2,29));assert (result.years,result.months,result.days)==(0,1,0) and result.text()=='1 month'
    result=calendar_interval(date(2024,1,31),date(2024,3,30));assert (result.months,result.days)==(1,30)
    assert calendar_interval(date(2024,2,29),date(2025,2,28)).years==1

def test_reverse_zero_and_wallclock_remainder():
    "Verify reverse zero and wallclock remainder."
    from humanize.calendar import calendar_interval
    a=datetime(2024,1,1);b=datetime(2024,2,2,1,2,3,4)
    forward=calendar_interval(a,b);reverse=calendar_interval(b,a)
    assert (forward.months,forward.days,forward.seconds,forward.microseconds)==(1,1,3723,4)
    assert reverse.sign==-1 and reverse.months==forward.months and reverse.text().startswith('-')
    assert calendar_interval(date(2024,1,1),date(2024,1,1)).text()=='0 days'

def test_timezone_validation_and_original_duration_api():
    "Verify timezone validation and original duration api."
    from humanize.calendar import calendar_interval
    a=datetime(2024,1,1,tzinfo=timezone.utc);b=datetime(2024,2,1,9,tzinfo=timezone(timedelta(hours=9)))
    assert calendar_interval(a,b).months==1
    with pytest.raises(ValueError):calendar_interval(a,datetime(2024,2,1))
    with pytest.raises(TypeError):calendar_interval(date(2024,1,1),datetime(2024,1,1))
    assert isinstance(humanize.naturaldelta(timedelta(days=29)),str)
