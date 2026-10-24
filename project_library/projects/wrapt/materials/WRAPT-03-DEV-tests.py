"""重复await复用完成值，异常/取消与不同loop不串缓存。"""
import asyncio
import unittest
from wrapt.async_cache import async_lru_cache

def test_completed_values_repeat_await_and_event_loop_isolation():
    """缓存的是结果，不是只能await一次的协程。@return None。"""
    calls=[]
    @async_lru_cache(maxsize=2)
    async def value(x):calls.append(x);await asyncio.sleep(0);return x*2
    async def run():
        assert await value(2)==await value(2)==4
        assert value.cache_info().hits==1 and value.cache_info().currsize==1
    asyncio.run(run());asyncio.run(run());assert calls==[2,2]

def test_failure_cancellation_and_clear_during_compute_do_not_store():
    """取消/失败不缓存，clear后迟到成功不回填。@return None。"""
    async def run():
        started=asyncio.Event();release=asyncio.Event();calls=[]
        @async_lru_cache(maxsize=2)
        async def blocked(x):calls.append(x);started.set();await release.wait();return x
        task=asyncio.create_task(blocked(1));await started.wait();blocked.cache_clear();release.set();assert await task==1
        assert blocked.cache_info().currsize==0
        @async_lru_cache()
        async def fail():raise ValueError('bad')
        for _ in range(2):
            with unittest.TestCase().assertRaises(ValueError):await fail()
        assert fail.cache_info().misses==2 and fail.cache_info().currsize==0
        started.clear();release.clear();task=asyncio.create_task(blocked(2));await started.wait();task.cancel()
        with unittest.TestCase().assertRaises(asyncio.CancelledError):await task
        assert blocked.cache_info().currsize==0
    asyncio.run(run())

