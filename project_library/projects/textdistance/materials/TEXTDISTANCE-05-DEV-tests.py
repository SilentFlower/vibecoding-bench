"""阈内精确、阈外None，用户无需分配完整长矩阵。"""
import unittest
from textdistance.bounded import bounded_levenshtein


def test_exact_boundary_zero_and_units():
    """恰好阈值保留，长度差下界及词单元正确。@return None。"""
    assert bounded_levenshtein('kitten','sitting',3)==3
    assert bounded_levenshtein('kitten','sitting',2) is None
    assert bounded_levenshtein('same','same',0)==0
    assert bounded_levenshtein('a','b',0) is None
    assert bounded_levenshtein('one two','one three',1,qval=None)==1
    assert bounded_levenshtein('A','a',0,test_func=lambda a,b:a.casefold()==b.casefold())==0


def test_length_gate_and_invalid_threshold():
    """长度差无需调用相等谓词；坏阈值不能被当数字。@return None。"""
    def forbidden(a,b):
        """下界已拒绝时不应比较。@param a 单元。@param b 单元。@return 不返回。"""
        raise AssertionError('不应执行')
    assert bounded_levenshtein('x'*100000,'',1,test_func=forbidden) is None
    for cutoff in (-1,True,0.5):
        with unittest.TestCase().assertRaises(ValueError):bounded_levenshtein('a','b',cutoff)

