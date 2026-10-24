"""报价生效时间关联用最后一个不晚于左事件的真实版本。"""
import unittest
from more_itertools import asof_join

def test_last_duplicate_before_left_and_tolerance():
    """相同右时间取最后版本，未来报价不能提前生效。@return None。"""
    left=[(0,'order0'),(2,'order2'),(5,'order5'),(9,'order9')]
    right=[(1,'v1'),(2,'old'),(2,'new'),(6,'v6')]
    result=list(asof_join(left,right,lambda value:value[0],tolerance=2,default='missing'))
    assert result==[(left[0],'missing'),(left[1],right[2]),(left[2],'missing'),(left[3],'missing')]
    assert list(asof_join(left,right,lambda value:value[0]))[-1][1] is right[-1]

def test_empty_one_shot_distinct_keys_and_invalid_order():
    """不用物化全表，左右可有不同时间字段。@return None。"""
    left=[{'at':2}];right=[{'since':1}]
    assert list(asof_join(iter(left),iter(right),lambda value:value['at'],right_key=lambda value:value['since']))==[(left[0],right[0])]
    assert list(asof_join(left,[],lambda value:value['at']))==[(left[0],None)]
    with unittest.TestCase().assertRaises(ValueError):list(asof_join([(2,),(1,)],[],lambda value:value[0]))
    with unittest.TestCase().assertRaises(ValueError):list(asof_join([(9,)],[(2,),(1,)],lambda value:value[0]))

