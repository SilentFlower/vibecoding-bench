"""按业务配额确定混流，源内顺序与耗尽收口明确。"""
from itertools import count,islice
import unittest
from more_itertools import interleave_weighted

def test_two_to_one_prefix_and_early_exhaustion():
    """耗尽退出后其余源继续，不补造重复项。@return None。"""
    assert list(interleave_weighted([1,2,3,4,5],['a','b'],weights=[2,1]))==[1,2,'a',3,4,'b',5]
    assert list(interleave_weighted([],['a','b'],[8],weights=[2,1,3]))==['a',8,'b']

def test_infinite_source_finite_prefix_and_invalid_weights():
    """只消费请求前缀，不提前缓存无界输入。@return None。"""
    assert list(islice(interleave_weighted(count(),count(100),weights=[2,1]),6))==[0,1,100,2,3,101]
    for weights in ([0,1],[-1,1],[1], [True,1]):
        with unittest.TestCase().assertRaises((ValueError,TypeError)):list(interleave_weighted([1],[2],weights=weights))

