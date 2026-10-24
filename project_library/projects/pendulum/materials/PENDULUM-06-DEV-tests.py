"""工作日历只用调用方假日，原始add日历语义不变。"""
from datetime import date
import unittest
import pendulum
from pendulum.business import BusinessCalendar

def test_holidays_weekends_both_directions_and_halfopen_count():
    """星期五加一工作日跳周末与周一假日。@return None。"""
    calendar=BusinessCalendar({date(2024,1,8)})
    friday=pendulum.date(2024,1,5)
    assert calendar.add_business_days(friday,1)==pendulum.date(2024,1,9)
    assert calendar.add_business_days(pendulum.date(2024,1,9),-1)==friday
    assert calendar.count(friday,pendulum.date(2024,1,10))==2
    assert calendar.count(pendulum.date(2024,1,10),friday)==-2

def test_policy_is_frozen_start_nonbusiness_and_zero_is_identity():
    """复制可变输入，保时区与钟点且不联网取假日。@return None。"""
    source={date(2024,1,8)};calendar=BusinessCalendar(source);source.clear()
    value=pendulum.datetime(2024,1,6,12,tz='Europe/Paris')
    assert calendar.add_business_days(value,1)==pendulum.datetime(2024,1,9,12,tz='Europe/Paris')
    assert calendar.add_business_days(value,0) is value
    with unittest.TestCase().assertRaises(ValueError):BusinessCalendar(weekend=set(range(7)))

