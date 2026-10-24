"""计时协程真实await区间，正常、异常和取消都在结束后输出。"""
import asyncio
from icecream import IceCreamDebugger
import pytest

def test_output_after_await_and_metadata_value():
    """调用只创建协程时不输出，执行结束才报告。@return None。"""
    output=[];events=[];debug=IceCreamDebugger(outputFunction=lambda value:(events.append('output'),output.append(value)))
    async def original(value):
        """原业务文档。"""
        events.append('start');await asyncio.sleep(0);events.append('end');return value
    wrapped=debug.timer(original);coroutine=wrapped(7);assert output==[]
    assert asyncio.run(coroutine)==7 and events==['start','end','output'] and 'original took ' in output[0]
    assert wrapped.__name__=='original' and wrapped.__doc__==original.__doc__

def test_exception_cancel_and_disabled_cleanup():
    """协程异常与取消保持，禁用不会留下未await协程。@return None。"""
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
    """同一装饰器在两个任务各自收口，不混用起点栈。@return None。"""
    output=[];timer=IceCreamDebugger(outputFunction=output.append).timer
    @timer
    async def recurse(n):
        await asyncio.sleep(0)
        return await recurse(n-1)+1 if n else 0
    async def run():return await asyncio.gather(recurse(1),recurse(2))
    assert asyncio.run(run())==[1,2] and len(output)==5
