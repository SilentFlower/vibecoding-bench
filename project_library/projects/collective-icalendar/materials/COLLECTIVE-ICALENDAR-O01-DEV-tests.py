"""CLI实际显示必须与Event日期语义一致。"""
from datetime import date, datetime, timedelta, timezone
from icalendar import Event

def test_all_day_default_end():
    """仅DATE DTSTART的事件结束于次日且持续一天。@return None。"""
    from icalendar.cli import view
    event = Event()
    event.add('dtstart', date(2026, 10, 22))
    rendered = view(event)
    assert date(2026, 10, 23).strftime('%c') in rendered
    assert str(timedelta(days=1)) in rendered

def test_timed_without_end_is_zero():
    """普通时间事件不擅自加一天。@return None。"""
    from icalendar.cli import view
    event = Event()
    event.add('dtstart', datetime(2026, 10, 22, 10, tzinfo=timezone.utc))
    assert '0:00:00' in view(event)

def test_explicit_duration_and_invalid_combination():
    """显式时长保持，非法DTEND+DURATION由真实模型拒绝。@return None。"""
    import pytest
    from icalendar.cli import view
    event = Event()
    event.add('dtstart', date(2026, 1, 1))
    event.add('duration', timedelta(days=3))
    assert '3 days' in view(event)
    event.add('dtend', date(2026, 1, 3))
    with pytest.raises(ValueError): view(event)
