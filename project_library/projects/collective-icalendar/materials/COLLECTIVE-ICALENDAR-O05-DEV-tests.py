"""平移整组日程必须保留主项与例外的对应关系。"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event, Alarm

def test_master_exception_and_recurrence_dates():
    """主项、覆盖、RDATE/EXDATE和UNTIL一起移动。@return None。"""
    from icalendar.schedule_shift import shift_schedule
    calendar = Calendar()
    event = Event(); event.add('UID', 'series'); event.add('DTSTART', date(2026, 1, 1)); event.add('DTEND', date(2026, 1, 2))
    event.add('RRULE', {'FREQ': 'DAILY', 'UNTIL': date(2026, 1, 10)})
    event.add('EXDATE', date(2026, 1, 3)); event.add('RDATE', date(2026, 1, 12))
    override = Event(); override.add('UID', 'series'); override.add('RECURRENCE-ID', date(2026, 1, 4)); override.add('DTSTART', date(2026, 1, 5))
    calendar.add_component(event); calendar.add_component(override)
    result = shift_schedule(calendar, timedelta(days=7))
    shifted, exception = result.walk('VEVENT')
    assert shifted.decoded('DTSTART') == date(2026, 1, 8) and exception.decoded('RECURRENCE-ID') == date(2026, 1, 11)
    assert shifted['EXDATE'].dts[0].dt == date(2026, 1, 10) and shifted['RRULE']['UNTIL'] == date(2026, 1, 17)
    assert event.decoded('DTSTART') == date(2026, 1, 1)

def test_dst_wall_vs_absolute():
    """DST跨越时墙钟日与24小时绝对偏移明确不同。@return None。"""
    from icalendar.schedule_shift import shift_schedule
    event = Event(); event.add('DTSTART', datetime(2026, 3, 7, 12, tzinfo=ZoneInfo('America/New_York')))
    assert shift_schedule(event, timedelta(days=1), mode='wall').decoded('DTSTART').hour == 12
    assert shift_schedule(event, timedelta(days=1), mode='absolute').decoded('DTSTART').hour == 13

def test_alarm_policy_and_date_rejection():
    """绝对提醒必须显式移动，相对提醒及DATE精度保持。@return None。"""
    import pytest
    from icalendar.schedule_shift import shift_schedule
    event = Event(); event.add('DTSTART', datetime(2026, 1, 1, tzinfo=timezone.utc))
    alarm = Alarm(); alarm.add('TRIGGER', datetime(2026, 1, 1, tzinfo=timezone.utc)); event.add_component(alarm)
    assert shift_schedule(event, timedelta(days=1)).walk('VALARM')[0].decoded('TRIGGER') == alarm.decoded('TRIGGER')
    assert shift_schedule(event, timedelta(days=1), shift_absolute_alarms=True).walk('VALARM')[0].decoded('TRIGGER') == datetime(2026, 1, 2, tzinfo=timezone.utc)
    all_day = Event(); all_day.add('DTSTART', date(2026, 1, 1))
    with pytest.raises(ValueError): shift_schedule(all_day, timedelta(hours=1))
