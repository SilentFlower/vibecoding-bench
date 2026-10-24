"Public regression tests for COLLECTIVE-ICALENDAR-O06-DEV; the complete business contract is in materials/COLLECTIVE-ICALENDAR-O06-DEV-contract.md."
from datetime import date, datetime, timezone
from icalendar import Calendar, Event

def test_property_and_component_order():
    "Verify property and component order."
    from icalendar.fingerprint import calendar_fingerprint
    one, two = Calendar(), Calendar()
    a = Event(); a.add('UID', 'a'); a.add('SUMMARY', 'A'); a.add('DTSTART', date(2026, 1, 1))
    b = Event(); b.add('DTSTART', date(2026, 1, 2)); b.add('UID', 'b')
    one.add_component(a); one.add_component(b)
    two.add_component(b.copy(recursive=True)); two.add_component(a.copy(recursive=True))
    assert calendar_fingerprint(one) == calendar_fingerprint(two)

def test_real_changes_and_explicit_ignore():
    "Verify real changes and explicit ignore."
    from icalendar.fingerprint import calendar_fingerprint
    event = Event(); event.add('UID', 'a'); event.add('SUMMARY', 'A')
    other = event.copy(recursive=True); other['SUMMARY'] = 'B'
    assert calendar_fingerprint(event) != calendar_fingerprint(other)
    other = event.copy(recursive=True); other.add('DTSTAMP', datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert calendar_fingerprint(event) != calendar_fingerprint(other)
    assert calendar_fingerprint(event, ignore_fields=['DTSTAMP']) == calendar_fingerprint(other, ignore_fields=['dtstamp'])

def test_unknown_preserved_and_bad_profile():
    "Verify unknown preserved and bad profile."
    import pytest
    from icalendar.fingerprint import calendar_fingerprint
    event = Event(); event.add('X-PRIVATE', 'one')
    other = Event(); other.add('X-PRIVATE', 'two')
    assert calendar_fingerprint(event)['digest'] != calendar_fingerprint(other)['digest']
    with pytest.raises(ValueError): calendar_fingerprint(event, ignore_fields=['SUMMARY'])
