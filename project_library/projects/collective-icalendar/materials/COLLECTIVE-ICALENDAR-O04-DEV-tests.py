"Public regression tests for COLLECTIVE-ICALENDAR-O04-DEV; the complete business contract is in materials/COLLECTIVE-ICALENDAR-O04-DEV-contract.md."
from datetime import datetime, timedelta, timezone
from icalendar import Todo

def test_complete_utc_and_original():
    "Verify complete utc and original."
    from icalendar.todo_transition import transition_todo
    source = Todo()
    moment = datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=8)))
    result = transition_todo(source, 'complete', completed_at=moment)
    assert str(result['STATUS']) == 'COMPLETED' and int(result['PERCENT-COMPLETE']) == 100
    assert result.decoded('COMPLETED') == moment.astimezone(timezone.utc)
    assert 'COMPLETED' not in source

def test_reopen_cancel_sequence_policy():
    "Verify reopen cancel sequence policy."
    from icalendar.todo_transition import transition_todo
    source = transition_todo(Todo(), 'complete', completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    reopened = transition_todo(source, 'reopen', progress=25, bump_sequence=True)
    assert str(reopened['STATUS']) == 'IN-PROCESS' and 'COMPLETED' not in reopened and int(reopened['SEQUENCE']) == 1
    assert str(transition_todo(reopened, 'cancel')['STATUS']) == 'CANCELLED'

def test_invalid_progress_and_naive():
    "Verify invalid progress and naive."
    import pytest
    from icalendar.todo_transition import transition_todo
    for progress in (-1, 100, True):
        with pytest.raises(ValueError): transition_todo(Todo(), 'reopen', progress=progress)
    with pytest.raises(ValueError): transition_todo(Todo(), 'complete', completed_at=datetime(2026, 1, 1))
