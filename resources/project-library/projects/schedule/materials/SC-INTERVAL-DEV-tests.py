"Public regression tests for SC-INTERVAL-DEV; the complete business contract is in materials/SC-INTERVAL-DEV-contract.md."
import datetime
import pytest
import schedule

def test_invalid_intervals_fail_at_construction():
    for value in (0,-1,float('nan'),float('inf'),True,'1',None):
        with pytest.raises(schedule.ScheduleValueError):
            schedule.Job(value)

def test_rejected_jobs_are_not_registered():
    scheduler=schedule.Scheduler()
    with pytest.raises(schedule.ScheduleValueError):
        scheduler.every(0).seconds.do(lambda:None)
    assert scheduler.jobs==[]

def test_positive_fractional_intervals_still_schedule():
    scheduler=schedule.Scheduler()
    before=datetime.datetime.now()
    job=scheduler.every(0.25).seconds.do(lambda:None)
    assert 0 < (job.next_run-before).total_seconds() < 1

def test_mutated_invalid_interval_and_fractional_random_are_rejected():
    job=schedule.Scheduler().every().seconds.do(lambda:None)
    job.interval=0
    with pytest.raises(schedule.ScheduleValueError):
        job._schedule_next_run()
    with pytest.raises(schedule.ScheduleValueError):
        schedule.Scheduler().every(0.5).to(2).seconds.do(lambda:None)
