"Public regression tests for PYTHON-DATEUTIL-01-DEV; the complete business contract is in materials/PYTHON-DATEUTIL-01-DEV-contract.md."
from datetime import datetime,timedelta
from io import StringIO
from dateutil.rrule import rrulestr
from dateutil.tz import tzical

def test_rrule_tab_and_space_continuations_produce_same_meetings():
    "Verify rrule tab and space continuations produce same meetings."
    for prefix in (' ','\t'):
        rule=rrulestr('DTSTART:20240101T090000\r\nRRULE:FREQ=DAILY;\r\n'+prefix+'COUNT=2',unfold=True)
        assert list(rule)==[datetime(2024,1,1,9),datetime(2024,1,2,9)]

def test_timezone_component_tab_unfold_is_applied_before_rule_parsing():
    "Verify timezone component tab unfold is applied before rule parsing."
    text='BEGIN:VTIMEZONE\nTZID:Local\nBEGIN:STANDARD\nDTSTART:20200101T000000\nTZOFFSETFROM:+0200\nTZOFFSETTO:+0\n\t200\nTZNAME:Local\nEND:STANDARD\nEND:VTIMEZONE'
    zone=tzical(StringIO(text)).get('Local')
    assert datetime(2024,1,1,tzinfo=zone).utcoffset()==timedelta(hours=2)

