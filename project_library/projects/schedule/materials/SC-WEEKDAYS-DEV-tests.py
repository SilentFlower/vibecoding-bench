"Public regression tests for SC-WEEKDAYS-DEV; the complete business contract is in materials/SC-WEEKDAYS-DEV-contract.md."
import datetime
import pytest
from unittest.mock import patch
import schedule

class Friday(datetime.datetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2026,10,23,12,0)

def test_weekend_skips_to_monday_at_the_same_clock():
    with patch.object(schedule.datetime,'datetime',Friday):
        job=schedule.Scheduler().every().day.on_weekdays(0,1,2,3,4).at('09:00').do(lambda:None)
    assert job.next_run==datetime.datetime(2026,10,26,9,0)

def test_later_allowed_time_today_is_preserved():
    with patch.object(schedule.datetime,'datetime',Friday):
        job=schedule.Scheduler().every().day.on_weekdays(4).at('18:30').do(lambda:None)
    assert job.next_run==datetime.datetime(2026,10,23,18,30)

def test_duplicate_days_are_harmless_and_invalid_days_fail():
    scheduler=schedule.Scheduler()
    assert scheduler.every().day.on_weekdays(0,0)._allowed_weekdays==frozenset({0})
    for days in ((),(7,),(-1,),(True,),('monday',)):
        with pytest.raises(schedule.ScheduleValueError):
            scheduler.every().day.on_weekdays(*days)

def test_incompatible_units_and_mutated_configuration_are_rejected():
    with pytest.raises(schedule.ScheduleValueError):
        schedule.Scheduler().every(2).days.on_weekdays(0)
    job=schedule.Scheduler().every().day.on_weekdays(0)
    job.interval=2
    with pytest.raises(schedule.ScheduleValueError):
        job.do(lambda:None)
