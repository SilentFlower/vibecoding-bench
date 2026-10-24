"Public regression tests for AP-ASYNC-DEV; the complete business contract is in materials/AP-ASYNC-DEV-contract.md."
import asyncio
import pytest
from alive_progress.asyncio import alive_async_it

def test_order_no_prefetch_and_completion_snapshot():
    async def scenario():
        seen=[];finished=[]
        async def source():
            for value in range(3):
                seen.append(value)
                yield value
        iterator=alive_async_it(source(),total=3,disable=True,finalize=lambda bar:finished.append(bar.snapshot()))
        assert await anext(iterator)==0 and seen==[0] and finished==[]
        rest=[value async for value in iterator]
        assert rest==[1,2] and finished[0].count==3
    asyncio.run(scenario())

def test_empty_input_and_awaitable_falsey_finalizer_run_once():
    async def scenario():
        calls=[]
        class Ending:
            def __bool__(self):
                return False
            async def __call__(self,bar):
                calls.append(bar.snapshot().count)
        async def source():
            if False:
                yield 1
        assert [value async for value in alive_async_it(source(),disable=True,finalize=Ending())]==[]
        assert calls==[0]
    asyncio.run(scenario())

def test_early_close_and_source_error_do_not_finalize():
    async def scenario():
        calls=[]
        async def source():
            yield 1
            raise LookupError('synthetic')
        iterator=alive_async_it(source(),disable=True,finalize=lambda bar:calls.append(1))
        assert await anext(iterator)==1
        await iterator.aclose()
        with pytest.raises(LookupError):
            async for value in alive_async_it(source(),disable=True,finalize=lambda bar:calls.append(1)):
                pass
        assert calls==[]
    asyncio.run(scenario())

def test_cancellation_propagates_and_keeps_success_callback_absent():
    async def scenario():
        calls=[]
        async def source():
            raise asyncio.CancelledError()
            yield 1
        with pytest.raises(asyncio.CancelledError):
            async for value in alive_async_it(source(),disable=True,finalize=lambda bar:calls.append(1)):
                pass
        assert calls==[]
    asyncio.run(scenario())
