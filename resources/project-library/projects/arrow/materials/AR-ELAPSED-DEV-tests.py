"Public regression tests for AR-ELAPSED-DEV; the complete business contract is in materials/AR-ELAPSED-DEV-contract.md."
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
import arrow

def test_fall_back_adjacent_instants_have_one_second_elapsed():
    before = arrow.get(datetime(2024,11,3,1,59,59,tzinfo=ZoneInfo('America/New_York'),fold=0))
    after = arrow.get(datetime(2024,11,3,1,0,0,tzinfo=ZoneInfo('America/New_York'),fold=1))
    assert after.elapsed(before) == timedelta(seconds=1)

def test_shift_elapsed_preserves_zone_and_correct_fold():
    before = arrow.get(datetime(2024,11,3,1,59,59,tzinfo=ZoneInfo('America/New_York'),fold=0))
    after = before.shift_elapsed(seconds=1)
    assert after.hour == 1 and after.minute == 0 and after.fold == 1
    assert after.elapsed(before) == timedelta(seconds=1)

def test_spring_forward_skips_nonexistent_wall_time():
    before = arrow.get(datetime(2024,3,10,1,30,tzinfo=ZoneInfo('America/New_York')))
    assert before.shift_elapsed(hours=1).hour == 3

def test_naive_and_calendar_units_are_rejected():
    value = arrow.get(2024,1,1)
    with pytest.raises(TypeError):
        value.elapsed(datetime(2024,1,1))
    with pytest.raises(ValueError):
        value.shift_elapsed(months=1)
    with pytest.raises(TypeError):
        value.shift_elapsed(seconds=True)

def test_microseconds_and_negative_shifts_are_exact():
    value = arrow.get(2024,1,1,0,0,0,123456)
    assert value.shift_elapsed(microseconds=-7).elapsed(value) == timedelta(microseconds=-7)

def test_existing_calendar_shift_and_original_value_are_unchanged():
    value = arrow.get(2024,1,31)
    assert value.shift(months=1).day == 29 and value.day == 31
