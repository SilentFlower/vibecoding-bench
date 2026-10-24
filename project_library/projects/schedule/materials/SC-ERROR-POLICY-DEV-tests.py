"""公开连续失败取消策略回归。"""
import pytest
import schedule
from schedule.policies import with_error_policy

def test_limit_cancels_job_and_notifies_original_exception():
    scheduler=schedule.Scheduler();errors=[];failure=ValueError('synthetic')
    def fail(value):
        assert value==3
        raise failure
    job=with_error_policy(scheduler.every().second.do(fail,3),max_failures=2,on_error=lambda error,count:errors.append((error,count)))
    scheduler._run_job(job);scheduler._run_job(job)
    assert job not in scheduler.jobs and errors==[(failure,1),(failure,2)]

def test_success_resets_consecutive_count_and_preserves_result():
    outcomes=iter([ValueError(),42,ValueError()])
    def callback():
        value=next(outcomes)
        if isinstance(value,Exception):
            raise value
        return value
    job=with_error_policy(schedule.Scheduler().every().second.do(callback),max_failures=2)
    assert job.run() is None and job.consecutive_failures==1
    assert job.run()==42 and job.consecutive_failures==0
    assert job.run() is None and job.consecutive_failures==1

def test_baseexception_and_handler_failure_propagate():
    def abort():
        raise KeyboardInterrupt()
    job=with_error_policy(schedule.Scheduler().every().second.do(abort))
    with pytest.raises(KeyboardInterrupt):
        job.run()

def test_unconfigured_double_wrap_and_invalid_limits_fail():
    with pytest.raises(schedule.ScheduleValueError):
        with_error_policy(schedule.Job(1))
    job=with_error_policy(schedule.Scheduler().every().second.do(lambda:None))
    with pytest.raises(schedule.ScheduleValueError):
        with_error_policy(job)
    with pytest.raises(schedule.ScheduleValueError):
        with_error_policy(job,max_failures=True)
