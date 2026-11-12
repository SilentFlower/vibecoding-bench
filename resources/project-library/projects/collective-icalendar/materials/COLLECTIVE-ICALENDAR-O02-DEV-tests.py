"Public regression tests for COLLECTIVE-ICALENDAR-O02-DEV; the complete business contract is in materials/COLLECTIVE-ICALENDAR-O02-DEV-contract.md."
from icalendar import Calendar, LazyCalendar


def test_mismatch_is_opt_in_and_legacy_unchanged():
    "Verify mismatch is opt in and legacy unchanged."
    import pytest
    raw = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nEND:VTODO\r\nEND:VCALENDAR\r\n'
    assert len(Calendar.from_ical(raw).walk('VEVENT')) == 1
    for calendar_type in (Calendar, LazyCalendar):
        with pytest.raises(ValueError, match='VEVENT'):
            calendar_type.from_ical_strict(raw)


def test_valid_nested_case_and_unknown_components():
    "Verify valid nested case and unknown components."
    raw = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT5M\r\nEND:valarm\r\nEND:vevent\r\nEND:vcalendar\r\n'
    for calendar_type in (Calendar, LazyCalendar):
        calendar = calendar_type.from_ical_strict(raw)
        assert len(calendar.walk('VALARM')) == 1
    custom = 'BEGIN:VCALENDAR\r\nBEGIN:X-CUSTOM\r\nX-VALUE:1\r\nEND:x-custom\r\nEND:VCALENDAR\r\n'
    assert Calendar.from_ical_strict(custom).subcomponents[0].name == 'X-CUSTOM'


def test_invalid_complete_input_precedes_parser_and_cache():
    "Verify invalid complete input precedes parser and cache."
    import pytest
    class Guard(Calendar):
        "Public regression fixture: Guard."
        @classmethod
        def _get_ical_parser(cls, st):
            "Support the public regression through _get_ical_parser."
            raise AssertionError('不应先构造解析器')
    valid = 'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'
    for raw in ('END:VCALENDAR\r\n', 'BEGIN:VCALENDAR\r\n', valid + 'END:X-OTHER\r\n',
        'BEGIN:VCALENDAR\r\nBEGIN:X-CUSTOM\r\nEND:VCALENDAR\r\nEND:X-CUSTOM\r\n'):
        with pytest.raises(ValueError):
            Guard.from_ical_strict(raw)


def test_bytes_path_multiple_and_subclass_dispatch(tmp_path):
    "Verify bytes path multiple and subclass dispatch."
    import pytest
    raw = b'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'
    path = tmp_path / 'strict.ics'
    path.write_bytes(raw + raw)
    assert len(Calendar.from_ical_strict(path, multiple=True)) == 2
    assert len(LazyCalendar.from_ical_strict(raw + raw, multiple=True)) == 2
    with pytest.raises(ValueError):
        Calendar.from_ical_strict(path)
    class Recording(Calendar):
        "Public regression fixture: Recording."
        observed = []
        @classmethod
        def _get_ical_parser(cls, st):
            "Support the public regression through _get_ical_parser."
            cls.observed.append(st)
            return super()._get_ical_parser(st)
    assert Recording.from_ical_strict(raw).name == 'VCALENDAR'
    assert Recording.observed == [raw]
