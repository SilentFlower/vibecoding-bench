"""公开真实状态配置快照回归。"""
from dataclasses import FrozenInstanceError
import pytest
from statemachine.snapshots import snapshot,freeze
from statemachine import StateMachine,State

class Flow(StateMachine):
    draft=State(initial=True)
    ready=State()
    done=State(final=True)
    advance=draft.to(ready)
    finish=ready.to(done)
    reset=ready.to(draft)

def test_snapshot_observes_actual_configuration_and_changes_only_after_send():
    machine=Flow();first=snapshot(machine);machine.send('advance');second=snapshot(machine)
    assert first.states==('draft',) and second.states==('ready',) and first.values==('draft',)
    assert set(second.allowed_events)=={'finish','reset'}

def test_snapshot_never_evaluates_guards():
    calls=[]
    class Guarded(StateMachine):
        start=State(initial=True);done=State(final=True)
        finish=start.to(done,cond=lambda:calls.append(1) or False)
    machine=Guarded();assert snapshot(machine).allowed_events==('finish',) and calls==[]

def test_frozen_result_and_nested_values_are_independent():
    original={'a':[1]};value=freeze(original);original['a'].append(2)
    assert value['a']==(1,)
    with pytest.raises(TypeError): value['a']=()
    result=snapshot(Flow())
    with pytest.raises(FrozenInstanceError): result.states=()

def test_invalid_values_are_rejected_instead_of_stringified():
    value=[];value.append(value)
    with pytest.raises(ValueError): freeze(value)
    with pytest.raises(TypeError): freeze(object())
