"""公开Excel日期系统转换回归。"""
from decimal import Decimal
import pytest
import arrow

def test_1900_epoch_and_leap_bug_boundaries():
    assert arrow.Arrow.from_excel(0, date_system='1900').format('YYYY-MM-DD') == '1899-12-31'
    assert arrow.Arrow.from_excel(59, date_system='1900').day == 28
    assert arrow.Arrow.from_excel(61, date_system='1900').format('YYYY-MM-DD') == '1900-03-01'
    with pytest.raises(ValueError):
        arrow.Arrow.from_excel(Decimal('60.5'), date_system='1900')

def test_1904_epoch_and_half_day():
    assert arrow.Arrow.from_excel(Decimal('0.5'), date_system='1904').format('YYYY-MM-DD HH:mm') == '1904-01-01 12:00'

def test_modern_dates_roundtrip_through_both_systems():
    value = arrow.get(2026, 3, 4, 12, 34, 56, 123456)
    for system in ('1900','1904'):
        assert arrow.Arrow.from_excel(value.to_excel(date_system=system), date_system=system) == value

def test_timezone_applies_to_wall_clock_not_unix_instant():
    value = arrow.Arrow.from_excel(Decimal('1.25'), date_system='1904', tzinfo='Asia/Shanghai')
    assert value.hour == 6 and value.utcoffset().total_seconds() == 28800
    assert value.to_excel(date_system='1904') == Decimal('1.25')

def test_bad_systems_booleans_and_nonfinite_serials_are_rejected():
    with pytest.raises(ValueError):
        arrow.Arrow.from_excel(1, date_system='guess')
    for value in (True, '123'):
        with pytest.raises(TypeError):
            arrow.Arrow.from_excel(value, date_system='1900')
    with pytest.raises(ValueError):
        arrow.Arrow.from_excel(float('inf'), date_system='1900')

def test_negative_serials_and_existing_unix_inputs():
    assert arrow.Arrow.from_excel(-1, date_system='1904').format('YYYY-MM-DD') == '1903-12-31'
    assert arrow.get(25569).int_timestamp == 25569
