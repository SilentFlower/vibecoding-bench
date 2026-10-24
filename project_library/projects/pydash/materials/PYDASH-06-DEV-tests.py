"Public regression tests for PYDASH-06-DEV; the complete business contract is in materials/PYDASH-06-DEV-contract.md."
import asyncio
import unittest
import pydash

def test_mixed_flow_runs_in_callers_loop_with_original_parameters():
    "Verify mixed flow runs in callers loop with original parameters."
    async def run():
        events=[]
        def first(x,*,offset):events.append('first');return x+offset
        async def second(x):await asyncio.sleep(0);events.append('second');return x*2
        def third(x):events.append('third');return {'total':x}
        assert await pydash.async_flow(first,second,third)(3,offset=2)=={'total':10}
        assert events==['first','second','third']
    asyncio.run(run())

def test_exception_cancellation_and_empty_chain_do_not_continue():
    "Verify exception cancellation and empty chain do not continue."
    async def run():
        seen=[]
        async def fail(x):raise ValueError('stage')
        with unittest.TestCase().assertRaises(ValueError):await pydash.async_flow(fail,lambda x:seen.append(x))(1)
        async def cancel(x):raise asyncio.CancelledError()
        with unittest.TestCase().assertRaises(asyncio.CancelledError):await pydash.async_flow(cancel,lambda x:seen.append(x))(1)
        assert seen==[] and await pydash.async_flow()(4)==4 and await pydash.async_flow()() is None
    asyncio.run(run())

