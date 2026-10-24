"""公开异步状态机实际事件回归。"""
import asyncio
import pytest
from statemachine.async_runner import AsyncMachineRunner
from statemachine import StateMachine,State

class Flow(StateMachine):
    draft=State(initial=True)
    ready=State()
    done=State(final=True)
    advance=draft.to(ready)
    finish=ready.to(done)
    reset=ready.to(draft)

def test_async_callback_is_completed_before_receipt_and_next_event():
    seen=[]
    class AsyncFlow(Flow):
        async def on_advance(self): await asyncio.sleep(0);seen.append('advance');return 7
        async def on_finish(self): seen.append('finish')
    async def scenario():
        machine=AsyncFlow();rows=[row async for row in AsyncMachineRunner(machine).run(['advance','finish'])]
        assert rows[0].after.states==('ready',) and rows[0].result==7 and rows[1].after.states==('done',)
    asyncio.run(scenario());assert seen==['advance','finish']

def test_async_source_is_lazy_and_collect_continues():
    calls=[]
    async def source():
        for event in ['finish','advance']: calls.append(event);yield event
    async def scenario():
        stream=AsyncMachineRunner(Flow()).run(source(),errors='collect');assert calls==[]
        rows=[row async for row in stream];assert [row.status for row in rows]==['error','passed']
    asyncio.run(scenario())

def test_cancelled_callback_is_not_converted_to_transition_error():
    class Cancelled(Flow):
        async def on_advance(self): raise asyncio.CancelledError()
    async def scenario():
        with pytest.raises(asyncio.CancelledError): await AsyncMachineRunner(Cancelled()).dispatch('advance',errors='collect')
    asyncio.run(scenario())

def test_invalid_strategy_is_checked_before_async_source_consumption():
    with pytest.raises(ValueError): AsyncMachineRunner(Flow()).run([],errors='skip')
