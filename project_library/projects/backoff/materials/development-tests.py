"""公开回归：有限等待耗尽与放弃政策在同步及异步中一致。"""
import asyncio
from unittest.mock import patch

import backoff
import pytest


def test_sync_exhaustion_respects_false():
    """耗尽不覆盖明确要求的None返回，回调只执行一次。@return None。"""
    calls, given = [], []
    @backoff.on_exception(backoff.constant, ValueError, interval=[], jitter=None,
        logger=None, raise_on_giveup=False, on_giveup=given.append)
    def send():
        """模拟一次失败发送。@return 不返回。"""
        calls.append(1)
        raise ValueError('not sent')
    assert send() is None
    assert len(calls) == len(given) == 1
    assert isinstance(given[0]['exception'], ValueError)


def test_async_exhaustion_respects_false():
    """异步耗尽采用相同政策并等待放弃回调。@return None。"""
    calls, given = [], []
    async def record(details):
        """保存真实异步回调详情。@param details 详情。@return None。"""
        given.append(details)
    @backoff.on_exception(backoff.constant, OSError, interval=[0], jitter=None,
        logger=None, raise_on_giveup=False, on_giveup=record)
    async def send():
        """模拟异步发送失败。@return 不返回。"""
        calls.append(1)
        raise OSError('offline')
    assert asyncio.run(send()) is None
    assert len(calls) == 2 and len(given) == 1 and given[0]['tries'] == 2


def test_raise_true_preserves_original_exception():
    """默认和显式抛出政策保持同一个异常对象。@return None。"""
    failure = LookupError('same instance')
    @backoff.on_exception(backoff.constant, LookupError, interval=[], logger=None)
    def send():
        """抛出固定异常。@return 不返回。"""
        raise failure
    with pytest.raises(LookupError) as caught:
        send()
    assert caught.value is failure


def test_success_and_predicate_controls():
    """正常成功和predicate耗尽仍返回业务结果。@return None。"""
    success = backoff.on_exception(backoff.constant, ValueError, interval=[], logger=None)(lambda: 19)
    predicate = backoff.on_predicate(backoff.constant, interval=[], logger=None)(lambda: 0)
    assert success() == 19 and predicate() == 0
