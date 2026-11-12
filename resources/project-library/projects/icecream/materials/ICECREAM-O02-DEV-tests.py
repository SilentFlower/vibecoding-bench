"Public regression tests for ICECREAM-O02-DEV; the complete business contract is in materials/ICECREAM-O02-DEV-contract.md."
from icecream import IceCreamDebugger
import icecream.icecream as module
import pytest

def test_reused_timer_nested_exact_durations(monkeypatch):
    "Verify reused timer nested exact durations."
    output=[];timer=IceCreamDebugger(outputFunction=output.append).timer;times=iter([0,1,3,5])
    monkeypatch.setattr(module.time,'perf_counter',lambda:next(times))
    with timer:
        with timer:pass
    assert output==['2.00s','5.00s'] and timer._enter_time is None
    with pytest.raises(RuntimeError):timer.__exit__(None,None,None)

def test_exception_and_output_failure_do_not_leave_entry(monkeypatch):
    "Verify exception and output failure do not leave entry."
    def broken(message):raise OSError('sink')
    timer=IceCreamDebugger(outputFunction=broken).timer
    with pytest.raises(ValueError,match='business'):
        with timer:raise ValueError('business')
    assert timer._enter_time is None
    with pytest.raises(OSError):
        with timer:pass
    assert timer._enter_time is None

def test_child_task_cannot_exit_parent_frame_and_disabled():
    "Verify child task cannot exit parent frame and disabled."
    import asyncio
    output=[];debug=IceCreamDebugger(outputFunction=output.append);timer=debug.timer
    async def run():
        with timer:
            async def child():
                with pytest.raises(RuntimeError):timer.__exit__(None,None,None)
                with timer:pass
            await asyncio.create_task(child())
    asyncio.run(run());assert len(output)==2
    debug.disable()
    with timer:
        with timer:pass
    assert len(output)==2
