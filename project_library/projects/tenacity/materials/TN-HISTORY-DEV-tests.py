"""公开有界无载荷尝试历史回归。"""
import asyncio
import pytest
from tenacity import Retrying,AsyncRetrying,stop_after_attempt
from tenacity.history import RetryHistory

def test_retry_attempts_and_success_are_recorded_with_bounds():
    history=RetryHistory(2);calls=[];result=object()
    def work(secret):
        calls.append(secret)
        if len(calls)<3:
            raise ValueError('private')
        return result
    assert Retrying(stop=stop_after_attempt(4),sleep=lambda _:None)(history.wrap(work),'secret') is result
    records=history.records
    assert [r.sequence for r in records]==[2,3] and [r.succeeded for r in records]==[False,True]
    assert records[0].exception_type=='builtins.ValueError' and all(r.elapsed>=0 for r in records)
    assert 'secret' not in repr(records) and 'private' not in repr(records)

def test_clear_does_not_reuse_sequence_and_snapshot_is_stable():
    history=RetryHistory();wrapped=history.wrap(lambda:1)
    wrapped();snapshot=history.records;history.clear();wrapped()
    assert snapshot[0].sequence==1 and history.records[0].sequence==2

def test_same_exception_object_is_propagated():
    history=RetryHistory();error=LookupError('private')
    def fail():
        raise error
    with pytest.raises(LookupError) as caught:
        history.wrap(fail)()
    assert caught.value is error and history.records[0].exception_type=='builtins.LookupError'

def test_async_target_is_recorded_after_awaiting():
    history=RetryHistory()
    async def work():
        return 7
    wrapped=history.wrap(work);coroutine=wrapped()
    assert history.records==()
    assert asyncio.run(coroutine)==7 and history.records[0].succeeded
