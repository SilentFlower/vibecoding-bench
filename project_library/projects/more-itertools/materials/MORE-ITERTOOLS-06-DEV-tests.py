"""严格长度只在实际观察到不符时报告，不提前物化。"""
import unittest
from more_itertools import sized_iterator

def test_exact_short_long_zero_and_stable_reported_len():
    """len仍为声明值，不变成剩余项计数。@return None。"""
    value=sized_iterator(iter([1,2]),2,strict=True)
    assert next(value)==1 and len(value)==2 and list(value)==[2]
    assert list(sized_iterator([],0,strict=True))==[]
    for iterable,length in (([1],2),([1,2],1),([1],0)):
        with unittest.TestCase().assertRaises(ValueError):list(sized_iterator(iterable,length,strict=True))

def test_prefix_consumption_and_default_unchecked_policy():
    """额外项被取到时才错误，默认仍不校验历史契约。@return None。"""
    seen=[]
    def source():
        for value in range(5):seen.append(value);yield value
    value=sized_iterator(source(),1,strict=True)
    assert next(value)==0 and seen==[0]
    with unittest.TestCase().assertRaises(ValueError):next(value)
    assert seen==[0,1]
    assert list(sized_iterator([1,2],1))==[1,2]

