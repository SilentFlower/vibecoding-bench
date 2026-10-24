"""Todo动作必须同步更新状态进度和完成时间。"""
from datetime import datetime, timedelta, timezone
from icalendar import Todo

def test_complete_utc_and_original():
    """完成统一UTC及100%，原Todo保持。@return None。"""
    from icalendar.todo_transition import transition_todo
    source = Todo()
    moment = datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=8)))
    result = transition_todo(source, 'complete', completed_at=moment)
    assert str(result['STATUS']) == 'COMPLETED' and int(result['PERCENT-COMPLETE']) == 100
    assert result.decoded('COMPLETED') == moment.astimezone(timezone.utc)
    assert 'COMPLETED' not in source

def test_reopen_cancel_sequence_policy():
    """重开清完成字段，版本变化仅显式执行。@return None。"""
    from icalendar.todo_transition import transition_todo
    source = transition_todo(Todo(), 'complete', completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    reopened = transition_todo(source, 'reopen', progress=25, bump_sequence=True)
    assert str(reopened['STATUS']) == 'IN-PROCESS' and 'COMPLETED' not in reopened and int(reopened['SEQUENCE']) == 1
    assert str(transition_todo(reopened, 'cancel')['STATUS']) == 'CANCELLED'

def test_invalid_progress_and_naive():
    """非法进度或无时区完成时间拒绝。@return None。"""
    import pytest
    from icalendar.todo_transition import transition_todo
    for progress in (-1, 100, True):
        with pytest.raises(ValueError): transition_todo(Todo(), 'reopen', progress=progress)
    with pytest.raises(ValueError): transition_todo(Todo(), 'complete', completed_at=datetime(2026, 1, 1))
