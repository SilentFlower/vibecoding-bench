"Public regression tests for ICECREAM-O03-DEV; the complete business contract is in materials/ICECREAM-O03-DEV-contract.md."
import asyncio
from icecream import IceCreamDebugger
import pytest

def test_output_after_await_and_metadata_value():
    "Verify output after await and metadata value."
    output=[];events=[];debug=IceCreamDebugger(outputFunction=lambda value:(events.append('output'),output.append(value)))
    async def original(value):
        "Support the public regression through original."
        events.append('start');await asyncio.sleep(0);events.append('end');return value
    wrapped=debug.timer(original);coroutine=wrapped(7);assert output==[]
    assert asyncio.run(coroutine)==7 and events==['start','end','output'] and 'original took ' in output[0]
    assert wrapped.__name__=='original' and wrapped.__doc__==original.__doc__

def test_exception_cancel_and_disabled_cleanup():
    "Verify exception cancel and disabled cleanup."
    output=[];debug=IceCreamDebugger(outputFunction=output.append);timer=debug.timer
    @timer
    async def fail():raise ValueError('business')
    with pytest.raises(ValueError):asyncio.run(fail())
    async def run():
        started=asyncio.Event()
        @timer
        async def blocked():started.set();await asyncio.Event().wait()
        task=asyncio.create_task(blocked());await started.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(run());assert len(output)==2
    debug.disable()
    with pytest.raises(ValueError):asyncio.run(fail())
    assert len(output)==2 and timer._enter_time is None

def test_shared_timer_interleaved_tasks_and_recursion():
    "Verify shared timer interleaved tasks and recursion."
    output=[];timer=IceCreamDebugger(outputFunction=output.append).timer
    @timer
    async def recurse(n):
        await asyncio.sleep(0)
        return await recurse(n-1)+1 if n else 0
    async def run():return await asyncio.gather(recurse(1),recurse(2))
    assert asyncio.run(run())==[1,2] and len(output)==5
