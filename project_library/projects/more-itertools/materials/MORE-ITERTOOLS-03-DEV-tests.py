"""窗口只缓存仍在真实事件时间范围内的项。"""
from datetime import datetime,timedelta
import unittest
from more_itertools import windowed_time

def test_dense_sparse_duplicate_and_lower_boundary_inclusive():
    """窗口为[t-span,t]，每个事件仅对应一个输出。@return None。"""
    events=[(0,'a'),(2,'b'),(2,'c'),(5,'d'),(10,'e')]
    result=list(windowed_time(iter(events),lambda event:event[0],3))
    assert result==[(events[0],),(events[0],events[1]),tuple(events[:3]),tuple(events[1:4]),(events[4],)]
    assert result[2][0] is events[0]

def test_datetime_empty_invalid_span_and_order():
    """固定时钟样本和倒序拒绝，无宿主实时依赖。@return None。"""
    start=datetime(2024,1,1);events=[start,start+timedelta(days=1)]
    assert list(windowed_time(events,lambda row:row,timedelta(days=1)))==[(start,),tuple(events)]
    assert list(windowed_time([],lambda row:row,1))==[]
    for events,span in (([2,1],1),([1],0)):
        with unittest.TestCase().assertRaises(ValueError):list(windowed_time(events,lambda row:row,span))

