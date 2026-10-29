"""核本地日历的日期类型、TEXT转义、参与者和重复规则载体。"""
from datetime import date, datetime, timedelta, timezone
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from zoneinfo import ZoneInfo

import icalendar
from icalendar import Calendar, Event, vCalAddress


def main() -> None:
    """仅用合成日历字符串核实际候选，不读取真实日历账号。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(icalendar.__file__).resolve() == root / 'library/src/icalendar/__init__.py'}
    task = argv[1]
    if task == 'IC-U01':
        event = Event()
        event.add('dtstart', date(2026, 10, 22))
        inferred = event.end
        event.add('dtend', date(2026, 10, 23))
        parsed = Event.from_ical(event.to_ical())
        result['all_day_date_events_use_an_exclusive_next_date_end'] = (
            b'DTSTART;VALUE=DATE:20261022' in event.to_ical()
            and type(parsed.decoded('dtstart')) is date and inferred == date(2026, 10, 23)
            and event.duration == timedelta(days=1) and parsed.end == date(2026, 10, 23))
    elif task == 'IC-U02':
        text = '计划,项目;路径\\test\n说明'
        event = Event()
        event.add('summary', text)
        raw = event.to_ical()
        result['calendar_text_escaping_roundtrips_the_actual_unicode_and_delimiters'] = (
            b'\\,' in raw and b'\\;' in raw and b'\\\\test' in raw and b'\\n' in raw
            and str(Event.from_ical(raw)['summary']) == text and b'\r\n' in raw)
    elif task == 'IC-C01':
        event = Event()
        first = vCalAddress('mailto:a@example.invalid')
        first.params['ROLE'] = 'REQ-PARTICIPANT'
        event.add('attendee', first)
        scalar = not isinstance(event['ATTENDEE'], list)
        event.add('ATTENDEE', 'mailto:b@example.invalid')
        parsed = Event.from_ical(event.to_ical())
        result['repeated_properties_preserve_multiple_values_and_per_value_parameters'] = (
            scalar and isinstance(parsed['attendee'], list)
            and [str(item) for item in parsed['attendee']] == ['mailto:a@example.invalid', 'mailto:b@example.invalid']
            and parsed['ATTENDEE'][0].params['ROLE'] == 'REQ-PARTICIPANT')
    elif task == 'IC-C02':
        forms = [datetime(2026, 10, 22, 9), datetime(2026, 10, 22, 9, tzinfo=ZoneInfo('Europe/Berlin')),
            datetime(2026, 10, 22, 9, tzinfo=timezone.utc)]
        decoded, encoded = [], []
        for value in forms:
            event = Event()
            event.add('dtstart', value)
            encoded.append(event.to_ical())
            decoded.append(Event.from_ical(encoded[-1]).decoded('dtstart'))
        result['floating_named_zone_and_utc_datetime_representations_have_distinct_meanings'] = (
            b'DTSTART:20261022T090000\r\n' in encoded[0] and decoded[0].tzinfo is None
            and b'DTSTART;TZID=Europe/Berlin:' in encoded[1] and decoded[1].utcoffset() == timedelta(hours=2)
            and b'DTSTART:20261022T090000Z' in encoded[2] and decoded[2].utcoffset() == timedelta(0))
    elif task == 'IC-P01':
        event = Event()
        event.add('uid', 'recurrence-local-001')
        event.add('dtstamp', datetime(2026, 1, 1, tzinfo=timezone.utc))
        event.add('dtstart', datetime(2026, 1, 1, 9, tzinfo=timezone.utc))
        event.add('rrule', {'freq': 'daily', 'count': 3})
        calendar = Calendar()
        calendar.add('prodid', '-//local synthetic fixture//')
        calendar.add('version', '2.0')
        calendar.add_component(event)
        components = Calendar.from_ical(calendar.to_ical()).walk('VEVENT')
        result['walking_a_recurring_event_returns_the_stored_component_not_expanded_occurrences'] = (
            len(components) == 1 and components[0]['RRULE']['COUNT'] == [3]
            and str(components[0]['UID']) == 'recurrence-local-001')
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
