"""更新参与状态时不能丢CN、ROLE、RSVP与委派参数。"""
from icalendar import Event
from icalendar.prop.cal_address import vCalAddress

def test_partial_update_preserves_parameters():
    """只改PARTSTAT，原组件及其他参数保持。@return None。"""
    from icalendar.attendee_update import upsert_attendee
    event = Event()
    attendee = vCalAddress('mailto:user@example.test', params={'CN': 'User', 'ROLE': 'REQ-PARTICIPANT', 'RSVP': 'TRUE'})
    event.attendees = [attendee]
    result = upsert_attendee(event, 'MAILTO:user@example.test', parameters={'PARTSTAT': 'ACCEPTED'})
    assert result.attendees[0].params['CN'] == 'User' and result.attendees[0].params['ROLE'] == 'REQ-PARTICIPANT'
    assert result.attendees[0].params['PARTSTAT'] == 'ACCEPTED' and 'PARTSTAT' not in event.attendees[0].params

def test_add_remove_and_case_policy():
    """URI scheme匹配但本地地址部分不擅自折叠。@return None。"""
    from icalendar.attendee_update import upsert_attendee, remove_attendee
    event = upsert_attendee(Event(), 'mailto:User@example.test', parameters={'CN': 'U'})
    result = upsert_attendee(event, 'mailto:user@example.test')
    assert len(result.attendees) == 2
    assert len(remove_attendee(result, 'MAILTO:user@example.test').attendees) == 1

def test_duplicate_policy_and_parameter_delete():
    """重复必须显式all，参数None可单独删除。@return None。"""
    import pytest
    from icalendar.attendee_update import upsert_attendee
    event = Event()
    event.attendees = [vCalAddress('mailto:a@x', params={'CN': 'A'}), vCalAddress('mailto:a@x', params={'CN': 'B'})]
    with pytest.raises(ValueError): upsert_attendee(event, 'mailto:a@x')
    result = upsert_attendee(event, 'mailto:a@x', parameters={'CN': None, 'PARTSTAT': 'TENTATIVE'}, duplicates='all')
    assert all('CN' not in item.params and item.params['PARTSTAT'] == 'TENTATIVE' for item in result.attendees)
