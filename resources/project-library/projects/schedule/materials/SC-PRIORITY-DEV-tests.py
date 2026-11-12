"Public regression tests for SC-PRIORITY-DEV; the complete business contract is in materials/SC-PRIORITY-DEV-contract.md."
import datetime
import pytest
import schedule

def test_equal_due_times_use_priority_then_registration_order():
    scheduler=schedule.Scheduler();events=[]
    jobs=[scheduler.every().day.do(events.append,name).set_priority(priority) for name,priority in [('low',0),('first',5),('second',5)]]
    for job in jobs:
        job.next_run=datetime.datetime(2020,1,1)
    scheduler.run_pending()
    assert events==['first','second','low']

def test_earlier_due_time_wins_over_priority():
    scheduler=schedule.Scheduler();events=[]
    older=scheduler.every().day.do(events.append,'older').set_priority(-10)
    newer=scheduler.every().day.do(events.append,'newer').set_priority(100)
    older.next_run=datetime.datetime(2020,1,1);newer.next_run=datetime.datetime(2020,1,2)
    scheduler.run_pending()
    assert events==['older','newer']

def test_canceljob_still_removes_only_that_job():
    scheduler=schedule.Scheduler();events=[]
    first=scheduler.every().day.do(lambda:schedule.CancelJob).set_priority(1)
    second=scheduler.every().day.do(events.append,'second')
    first.next_run=second.next_run=datetime.datetime(2020,1,1)
    scheduler.run_pending()
    assert scheduler.jobs==[second] and events==['second']

def test_invalid_priority_is_rejected():
    for value in (True,1.2,'1'):
        with pytest.raises(schedule.ScheduleValueError):
            schedule.Job(1).set_priority(value)
