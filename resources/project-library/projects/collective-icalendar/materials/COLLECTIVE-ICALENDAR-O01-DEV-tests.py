"Public regression tests for COLLECTIVE-ICALENDAR-O01-DEV; the complete business contract is in materials/COLLECTIVE-ICALENDAR-O01-DEV-contract.md."
from datetime import date, datetime, timedelta, timezone
from icalendar import Event

def test_all_day_default_end():
    "Verify all day default end."
    from icalendar.cli import view
    event = Event()
    event.add('dtstart', date(2026, 10, 22))
    rendered = view(event)
    assert date(2026, 10, 23).strftime('%c') in rendered
    assert str(timedelta(days=1)) in rendered

def test_timed_without_end_is_zero():
    "Verify timed without end is zero."
    from icalendar.cli import view
    event = Event()
    event.add('dtstart', datetime(2026, 10, 22, 10, tzinfo=timezone.utc))
    assert '0:00:00' in view(event)

def test_explicit_duration_and_invalid_combination():
    "Verify explicit duration and invalid combination."
    import pytest
    from icalendar.cli import view
    event = Event()
    event.add('dtstart', date(2026, 1, 1))
    event.add('duration', timedelta(days=3))
    assert '3 days' in view(event)
    event.add('dtend', date(2026, 1, 3))
    with pytest.raises(ValueError): view(event)
