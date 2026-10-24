"""区间点生成显式边界与上限，不改变原锚点月底策略。"""
import unittest
import pendulum

def test_closed_bounds_limit_reverse_and_month_anchor():
    """月末恢复仍由原锚点累计步数决定。@return None。"""
    a=pendulum.datetime(2023,1,31);b=pendulum.datetime(2023,4,30)
    value=pendulum.interval(a,b)
    assert [d.day for d in value.range('months')]==[31,28,31,30]
    assert [d.month for d in value.range('months',closed='left')]==[1,2,3]
    assert [d.month for d in value.range('months',closed='right',limit=2)]==[2,3]
    assert list(value.range('months',limit=0))==[]
    assert [d.day for d in pendulum.interval(pendulum.date(2024,1,3),pendulum.date(2024,1,1)).range('days',closed='left')]==[3,2]

def test_invalid_progress_units_and_single_point_policies():
    """零/负步长不得成为无限相同点，首尾同点按both包含。@return None。"""
    value=pendulum.interval(pendulum.date(2024,1,1),pendulum.date(2024,1,2))
    for kwargs in ({'amount':0},{'amount':-1},{'closed':'bad'},{'limit':-1}):
        with unittest.TestCase().assertRaises(ValueError):list(value.range('days',**kwargs))
    same=pendulum.interval(value.start,value.start)
    assert list(same.range('days'))==[value.start] and list(same.range('days',closed='neither'))==[]

