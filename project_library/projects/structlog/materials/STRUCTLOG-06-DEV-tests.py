"""业务时区输出有明确offset和小数精度，可注入固定时钟。"""
from datetime import datetime,timezone,timedelta
import unittest
from structlog.processors import ZonedTimeStamper

def test_fixed_zone_precision_conversion_and_event_identity():
    """真实瞬间转换而非简单改tzinfo标签。@return None。"""
    now=datetime(2024,1,1,23,59,59,123456,tzinfo=timezone.utc)
    stamp=ZonedTimeStamper(timezone(timedelta(hours=5,minutes=30)),timespec='milliseconds',key='at',clock=lambda:now)
    event={'event':'order'}
    assert stamp(None,'info',event) is event and event['at']=='2024-01-02T05:29:59.123+05:30'
    assert now.hour==23

def test_utc_name_invalid_clock_and_invalid_policy():
    """明确命名UTC可用，naive时钟拒绝而非猜本地。@return None。"""
    stamp=ZonedTimeStamper('UTC',timespec='seconds',clock=lambda:datetime(2024,1,1,tzinfo=timezone.utc))
    assert stamp(None,'info',{})['timestamp']=='2024-01-01T00:00:00+00:00'
    with unittest.TestCase().assertRaises(ValueError):ZonedTimeStamper(timezone.utc,clock=lambda:datetime(2024,1,1))(None,'info',{})
    with unittest.TestCase().assertRaises(ValueError):ZonedTimeStamper(timezone.utc,timespec='nanoseconds')

