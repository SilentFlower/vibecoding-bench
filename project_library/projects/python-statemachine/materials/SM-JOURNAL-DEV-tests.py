"Public regression tests for SM-JOURNAL-DEV; the complete business contract is in materials/SM-JOURNAL-DEV-contract.md."
import json
import pytest
from statemachine.runner import MachineRunner
from statemachine.journal import dumps_journal,loads_journal
from statemachine import StateMachine,State

class Flow(StateMachine):
    draft=State(initial=True)
    ready=State()
    done=State(final=True)
    advance=draft.to(ready)
    finish=ready.to(done)
    reset=ready.to(draft)

def test_actual_events_and_errors_round_trip_as_data_only():
    rows=list(MachineRunner(Flow()).run(['finish','advance','finish'],errors='collect'));document=dumps_journal(rows);restored=loads_journal(document)
    assert [row.call.event for row in restored]==['finish','advance','finish'] and restored[-1].after.states==('done',)
    assert restored[0].status=='error' and restored[1].before==rows[1].before

def test_empty_journal_and_unicode_arguments_are_supported():
    assert loads_journal(dumps_journal([]))==()
    rows=list(MachineRunner(Flow()).run(['advance']));data=json.loads(dumps_journal(rows));data['records'][0]['kwargs']={'text':'中文'}
    assert loads_journal(json.dumps(data))[0].call.kwargs=={'text':'中文'}

def test_bad_version_index_and_duplicate_keys_are_rejected():
    with pytest.raises(ValueError): loads_journal('{"schema":1,"schema":1,"records":[]}')
    with pytest.raises(ValueError): loads_journal('{"schema":2,"records":[]}')
    data=json.loads(dumps_journal(list(MachineRunner(Flow()).run(['advance']))));data['records'][0]['index']=2
    with pytest.raises(ValueError): loads_journal(json.dumps(data))

def test_count_budget_and_hidden_scheduling_fields_are_rejected():
    rows=list(MachineRunner(Flow()).run(['advance','finish']))
    with pytest.raises(ValueError): dumps_journal(rows,max_records=1)
    data=json.loads(dumps_journal(rows));data['records'][0]['kwargs']={'delay':4}
    with pytest.raises(ValueError): loads_journal(json.dumps(data))
