"Public regression tests for WRAPT-03-DEV; the complete business contract is in materials/WRAPT-03-DEV-contract.md."
import asyncio
import unittest
from wrapt.async_cache import async_lru_cache

def test_completed_values_repeat_await_and_event_loop_isolation():
    "Verify completed values repeat await and event loop isolation."
    calls=[]
    @async_lru_cache(maxsize=2)
    async def value(x):calls.append(x);await asyncio.sleep(0);return x*2
    async def run():
        assert await value(2)==await value(2)==4
        assert value.cache_info().hits==1 and value.cache_info().currsize==1
    asyncio.run(run());asyncio.run(run());assert calls==[2,2]

def test_failure_cancellation_and_clear_during_compute_do_not_store():
    "Verify failure cancellation and clear during compute do not store."
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

