"""公开真实状态机日志重放端到端回归。"""
import json
import pytest
from statemachine.runner import MachineRunner
from statemachine.journal import dumps_journal
from statemachine.replay import replay
from statemachine import StateMachine,State

class Flow(StateMachine):
    draft=State(initial=True)
    ready=State()
    done=State(final=True)
    advance=draft.to(ready)
    finish=ready.to(done)
    reset=ready.to(draft)

def test_actual_events_replay_on_fresh_factory_machine():
    original=Flow();document=dumps_journal(list(MachineRunner(original).run(['advance','reset','advance','finish'])))
    result=replay(Flow,document)
    assert result.machine is not original and result.results[-1].after.states==('done',) and tuple(original.configuration_values)==('done',)

def test_expected_disallowed_events_and_empty_log_are_supported():
    document=dumps_journal(list(MachineRunner(Flow()).run(['finish','advance'],errors='collect')))
    result=replay(Flow,document)
    assert [row.status for row in result.results]==['error','passed'] and replay(Flow,dumps_journal([])).results==()

def test_divergent_expected_configuration_is_not_silently_accepted():
    data=json.loads(dumps_journal(list(MachineRunner(Flow()).run(['advance']))));data['records'][0]['after']['states']=['done']
    with pytest.raises(ValueError,match='索引0'): replay(Flow,json.dumps(data))
    assert replay(Flow,json.dumps(data),verify=False).results[0].after.states==('ready',)

def test_invalid_log_is_rejected_before_factory_is_called():
    calls=[]
    def factory(): calls.append(1);return Flow()
    with pytest.raises(ValueError): replay(factory,'{"schema":2,"records":[]}')
    assert calls==[]
