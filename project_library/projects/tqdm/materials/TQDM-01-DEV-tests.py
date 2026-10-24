"""product重复数按整数索引协议计算真实组合量。"""
import itertools
import unittest
import numpy
from tqdm.contrib.itertools import product


class Recorder:
    """仅观察真实wrapper传入total，不替代itertools结果。"""
    totals=[]
    def __init__(self,iterable,**kwargs):
        """保存实际迭代器及总数。@param iterable 原product。@param kwargs 进度参数。@return None。"""
        self.iterable=iterable;self.totals.append(kwargs['total'])
    def __iter__(self):
        """透传组合。@return 原迭代器。"""
        return iter(self.iterable)


def test_index_object_and_arbitrary_precision_total():
    """自定义index及numpy整数不能指数溢出。@return None。"""
    class Repeat:
        """合法整数索引对象。"""
        def __index__(self):
            """返回重复数。@return 2。"""
            return 2
    assert list(product(range(3),repeat=Repeat(),tqdm_class=Recorder))==list(itertools.product(range(3),repeat=2))
    iterator=product(range(16),repeat=numpy.int64(16),tqdm_class=Recorder)
    assert next(iterator)==(0,)*16 and Recorder.totals[-1]==16**16
    iterator.close()


def test_zero_negative_noninteger_and_explicit_total():
    """标准repeat边界和调用方显式total政策保持。@return None。"""
    assert list(product([],repeat=0,tqdm_class=Recorder))==[()]
    assert list(product([1],repeat=2,total=99,tqdm_class=Recorder))==[(1,1)] and Recorder.totals[-1]==99
    with unittest.TestCase().assertRaises(ValueError):list(product([1],repeat=-1,tqdm_class=Recorder))
    with unittest.TestCase().assertRaises(TypeError):list(product([1],repeat=1.5,tqdm_class=Recorder))

