"Public regression tests for PYTHON-DATEUTIL-02-DEV; the complete business contract is in materials/PYTHON-DATEUTIL-02-DEV-contract.md."
from datetime import datetime
from dateutil.rrule import rrule,MONTHLY,FR,MO,YEARLY

def test_duplicate_ordinary_and_ordinal_friday_is_all_fridays():
    "Verify duplicate ordinary and ordinal friday is all fridays."
    values=list(rrule(MONTHLY,dtstart=datetime(2024,1,1),byweekday=(FR,FR(1)),count=5))
    assert values==[datetime(2024,1,5),datetime(2024,1,12),datetime(2024,1,19),datetime(2024,1,26),datetime(2024,2,2)]

def test_mixed_days_negative_ordinal_and_other_filters():
    "Verify mixed days negative ordinal and other filters."
    values=list(rrule(MONTHLY,dtstart=datetime(2024,1,1),byweekday=(MO,FR(-1)),count=6))
    assert values==[datetime(2024,1,1),datetime(2024,1,8),datetime(2024,1,15),datetime(2024,1,22),datetime(2024,1,26),datetime(2024,1,29)]
    values=list(rrule(YEARLY,dtstart=datetime(2024,1,1),bymonth=(1,),byweekday=(MO,FR(1)),bysetpos=-1,count=2))
    assert values==[datetime(2024,1,29),datetime(2025,1,27)]

