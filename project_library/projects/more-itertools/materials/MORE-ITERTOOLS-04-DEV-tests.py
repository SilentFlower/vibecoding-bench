"Public regression tests for MORE-ITERTOOLS-04-DEV; the complete business contract is in materials/MORE-ITERTOOLS-04-DEV-contract.md."
import unittest
from more_itertools import asof_join

def test_last_duplicate_before_left_and_tolerance():
    "Verify last duplicate before left and tolerance."
    left=[(0,'order0'),(2,'order2'),(5,'order5'),(9,'order9')]
    right=[(1,'v1'),(2,'old'),(2,'new'),(6,'v6')]
    result=list(asof_join(left,right,lambda value:value[0],tolerance=2,default='missing'))
    assert result==[(left[0],'missing'),(left[1],right[2]),(left[2],'missing'),(left[3],'missing')]
    assert list(asof_join(left,right,lambda value:value[0]))[-1][1] is right[-1]

def test_empty_one_shot_distinct_keys_and_invalid_order():
    "Verify empty one shot distinct keys and invalid order."
    left=[{'at':2}];right=[{'since':1}]
    assert list(asof_join(iter(left),iter(right),lambda value:value['at'],right_key=lambda value:value['since']))==[(left[0],right[0])]
    assert list(asof_join(left,[],lambda value:value['at']))==[(left[0],None)]
    with unittest.TestCase().assertRaises(ValueError):list(asof_join([(2,),(1,)],[],lambda value:value[0]))
    with unittest.TestCase().assertRaises(ValueError):list(asof_join([(9,)],[(2,),(1,)],lambda value:value[0]))

