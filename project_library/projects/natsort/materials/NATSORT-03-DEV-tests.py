"""前K结果与稳定全量自然排序前缀一致。"""
import unittest
from natsort import natsorted, ns
from natsort.topk import natural_topk


def test_forward_reverse_and_stability():
    """同键保留输入次序，反向也不颠倒平手。@return None。"""
    values=['x10','x2','x02','x1']
    for reverse in (False,True):
        assert natural_topk(iter(values),3,reverse=reverse)==natsorted(values,reverse=reverse)[:3]
    assert natural_topk(values,3,indices=True)==[3,1,2]


def test_zero_never_consumes_and_negative_rejects():
    """零数量不触碰输入，非法数量明确失败。@return None。"""
    def forbidden():
        """证明输入没有被请求。@return 不返回。"""
        raise AssertionError('consumed')
        yield
    assert natural_topk(forbidden(),0)==[]
    with unittest.TestCase().assertRaises(ValueError):natural_topk([], -1)


def test_key_and_original_algorithm():
    """真实key与REAL算法继续生效。@return None。"""
    values=[{'v':'-1.5'},{'v':'2'},{'v':'-10.2'}]
    assert natural_topk(values,99,key=lambda x:x['v'],alg=ns.REAL)==natsorted(values,key=lambda x:x['v'],alg=ns.REAL)

