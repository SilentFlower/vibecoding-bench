"""显式严格入口覆盖完整文本，旧容错入口保持兼容。"""
from icalendar import Calendar, LazyCalendar


def test_mismatch_is_opt_in_and_legacy_unchanged():
    """严格入口拒绝错配，旧from_ical仍按冻结行为容错。@return None。"""
    import pytest
    raw = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nEND:VTODO\r\nEND:VCALENDAR\r\n'
    assert len(Calendar.from_ical(raw).walk('VEVENT')) == 1
    for calendar_type in (Calendar, LazyCalendar):
        with pytest.raises(ValueError, match='VEVENT'):
            calendar_type.from_ical_strict(raw)


def test_valid_nested_case_and_unknown_components():
    """严格入口保持大小写、合法嵌套和真实未知组件。@return None。"""
    raw = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT5M\r\nEND:valarm\r\nEND:vevent\r\nEND:vcalendar\r\n'
    for calendar_type in (Calendar, LazyCalendar):
        calendar = calendar_type.from_ical_strict(raw)
        assert len(calendar.walk('VALARM')) == 1
    custom = 'BEGIN:VCALENDAR\r\nBEGIN:X-CUSTOM\r\nX-VALUE:1\r\nEND:x-custom\r\nEND:VCALENDAR\r\n'
    assert Calendar.from_ical_strict(custom).subcomponents[0].name == 'X-CUSTOM'


def test_invalid_complete_input_precedes_parser_and_cache():
    """尾部损坏也必须在真实解析器、组件工厂和缓存之前被拒绝。@return None。"""
    import pytest
    class Guard(Calendar):
        """监测损坏结构是否错误进入模型解析。"""
        @classmethod
        def _get_ical_parser(cls, st):
            """禁止损坏输入调用解析器。@param st 输入。@return 不返回。"""
            raise AssertionError('不应先构造解析器')
    valid = 'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'
    for raw in ('END:VCALENDAR\r\n', 'BEGIN:VCALENDAR\r\n', valid + 'END:X-OTHER\r\n',
        'BEGIN:VCALENDAR\r\nBEGIN:X-CUSTOM\r\nEND:VCALENDAR\r\nEND:X-CUSTOM\r\n'):
        with pytest.raises(ValueError):
            Guard.from_ical_strict(raw)


def test_bytes_path_multiple_and_subclass_dispatch(tmp_path):
    """文件、字节、多组件及子类解析器均沿真实API。@return None。"""
    import pytest
    raw = b'BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'
    path = tmp_path / 'strict.ics'
    path.write_bytes(raw + raw)
    assert len(Calendar.from_ical_strict(path, multiple=True)) == 2
    assert len(LazyCalendar.from_ical_strict(raw + raw, multiple=True)) == 2
    with pytest.raises(ValueError):
        Calendar.from_ical_strict(path)
    class Recording(Calendar):
        """严格校验后仍必须使用真实子类解析入口。"""
        observed = []
        @classmethod
        def _get_ical_parser(cls, st):
            """记录输入并委托原解析器。@param st 文本。@return 解析器。"""
            cls.observed.append(st)
            return super()._get_ical_parser(st)
    assert Recording.from_ical_strict(raw).name == 'VCALENDAR'
    assert Recording.observed == [raw]
