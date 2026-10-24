"""跨timedelta相等的Interval必须共享hash，端点身份比较仍保持。"""
from datetime import timedelta
import pendulum

def test_interval_and_timedelta_equal_cache_key_hash_contract():
    """同一时长混用标准库与Pendulum时不产生重复键。@return None。"""
    start=pendulum.datetime(2024,1,1)
    for span in (timedelta(days=1),timedelta(seconds=-3),timedelta(microseconds=5)):
        value=pendulum.interval(start,start+span)
        assert value==span and hash(value)==hash(span)
        assert len({value,span})==1 and {value:'found'}[span]=='found'

def test_interval_endpoint_identity_equality_and_absolute_policy_stay():
    """同长但不同端点区间仍可不相等，哈希碰撞合法。@return None。"""
    first=pendulum.interval(pendulum.datetime(2024,1,1),pendulum.datetime(2024,1,2))
    second=pendulum.interval(pendulum.datetime(2024,2,1),pendulum.datetime(2024,2,2))
    same=pendulum.interval(first.start,first.end)
    assert first==same and hash(first)==hash(same) and first!=second
    assert len({first,second})==2

