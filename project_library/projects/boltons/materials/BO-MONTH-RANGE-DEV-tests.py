"""公开月度日期序列回归。"""
from datetime import date
import pytest
from boltons.timeutils import month_range

def test_clipped_february_does_not_shift_the_march_anchor():
    assert list(month_range(date(2024,1,31),date(2024,4,1)))==[date(2024,1,31),date(2024,2,29),date(2024,3,31)]

def test_skip_and_raise_policies_are_explicit():
    assert list(month_range(date(2023,1,31),date(2023,4,1),month_end='skip'))==[date(2023,1,31),date(2023,3,31)]
    with pytest.raises(ValueError):
        list(month_range(date(2023,1,31),date(2023,4,1),month_end='raise'))

def test_reverse_and_inclusive_boundaries_are_supported():
    assert list(month_range(date(2023,3,31),date(2023,1,31),-1,inclusive=True))==[date(2023,3,31),date(2023,2,28),date(2023,1,31)]

def test_invalid_steps_and_policies_fail():
    for options in ({'step':0},{'step':True},{'month_end':'guess'}):
        with pytest.raises(ValueError):
            list(month_range(date(2024,1,1),date(2024,2,1),**options))
