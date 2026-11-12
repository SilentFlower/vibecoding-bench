"Public regression tests for SM-RUNNER-DEV; the complete business contract is in materials/SM-RUNNER-DEV-contract.md."
import pytest
from statemachine.runner import MachineRunner,EventCall
from statemachine.exceptions import TransitionNotAllowed
from statemachine import StateMachine,State

class Flow(StateMachine):
    draft=State(initial=True)
    ready=State()
    done=State(final=True)
    advance=draft.to(ready)
    finish=ready.to(done)
    reset=ready.to(draft)

def test_actual_events_record_before_after_and_native_result():
    machine=Flow();result=MachineRunner(machine).dispatch('advance')
    assert result.before.states==('draft',) and result.after.states==('ready',) and result.status=='passed'

def test_collect_continues_after_transition_not_allowed():
    result=list(MachineRunner(Flow()).run(['finish','advance','finish'],errors='collect'))
    assert [row.status for row in result]==['error','passed','passed'] and result[2].after.states==('done',)

def test_stream_is_lazy_and_default_error_is_original_exception():
    machine=Flow();calls=[]
    def source(): calls.append(1);yield 'advance'
    stream=MachineRunner(machine).run(source());assert calls==[] and tuple(machine.configuration_values)==('draft',)
    assert next(stream).call.event=='advance' and calls==[1]
    with pytest.raises(TransitionNotAllowed): MachineRunner(Flow()).dispatch('finish')

def test_callback_arguments_are_detached_and_control_keywords_are_rejected():
    observed=[]
    class WithArgs(Flow):
        def on_advance(self,payload): payload.append('changed');observed.append(payload)
    value=[];result=MachineRunner(WithArgs()).dispatch(EventCall('advance',kwargs={'payload':value}))
    assert observed==[['changed']] and value==[]
    with pytest.raises(ValueError): MachineRunner(Flow()).dispatch(EventCall('advance',kwargs={'delay':1}))
