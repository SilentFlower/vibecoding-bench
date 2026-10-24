"""Duration日历分量减法与subtract声明保持一致。"""
from datetime import timedelta
import pendulum

def test_calendar_day_and_elapsed_hours_across_dst_are_distinct():
    """纽约跳时日减日历一天仍在前一天相同钟点。@return None。"""
    value=pendulum.datetime(2026,3,8,12,tz='America/New_York')
    assert value-pendulum.duration(days=1)==value.subtract(days=1)
    assert (value-pendulum.duration(days=1)).hour==12
    assert value-timedelta(days=1)==value.subtract(seconds=86400)

def test_mixed_calendar_signature_negative_and_month_end():
    """年/月/周/日与固定小时全部按原声明进入subtract。@return None。"""
    value=pendulum.datetime(2024,3,31,12,tz='Europe/Paris')
    options={'years':1,'months':1,'weeks':1,'days':2,'hours':3,'microseconds':7}
    assert value-pendulum.duration(**options)==value.subtract(**options)
    options={'days':-1,'hours':2}
    assert value-pendulum.duration(**options)==value.subtract(**options)

