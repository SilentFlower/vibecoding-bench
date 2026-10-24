"""倒序区间的无向覆盖与真实点迭代一致，方向不丢。"""
import pendulum

def test_reversed_and_forward_intervals_cover_same_members_and_endpoints():
    """周三到周一包含周二及两个端点。@return None。"""
    start=pendulum.date(2024,1,1);end=pendulum.date(2024,1,3)
    forward=pendulum.interval(start,end);reverse=pendulum.interval(end,start)
    for value in (start,start.add(days=1),end):
        assert value in forward and value in reverse
    assert start.subtract(days=1) not in reverse and end.add(days=1) not in reverse
    assert list(reverse.range('days'))==[end,start.add(days=1),start]

def test_same_endpoint_aware_datetime_and_original_direction():
    """修复成员判断不交换保存的端点或符号。@return None。"""
    a=pendulum.datetime(2024,1,1,tz='UTC');b=a.add(hours=2)
    value=pendulum.interval(b,a)
    assert a.add(hours=1) in value and value.start==b and value.end==a and value.invert
    assert a in pendulum.interval(a,a) and a.add(seconds=1) not in pendulum.interval(a,a)

