"""正负复数分量保持精度规则，并可被真实Diff与Hash使用。"""
from deepdiff import DeepDiff,DeepHash
from deepdiff.helper import number_to_string
import pytest

def test_sign_precision_and_exponential_matrix():
    """四象限、纯虚数、零精度都不能产生非法+-。@return None。"""
    for real in [-1.234,0,1.234]:
        for imag in [-2.345,0,2.345]:
            for notation in ['f','e']:
                result=number_to_string(complex(real,imag),2,notation)
                assert complex(result)==complex(float(number_to_string(real,2,notation)),float(number_to_string(imag,2,notation)))
    assert complex(number_to_string(1-2j,0))==1-2j

def test_actual_diff_hash_with_negative_imaginary():
    """真实比较和哈希不崩溃，并按精度相等。@return None。"""
    assert DeepDiff({'v':1-1.001j},{'v':1-1.002j},significant_digits=2)=={}
    assert DeepHash(1-2j,significant_digits=2)[1-2j]==DeepHash(1-2.001j,significant_digits=2)[1-2.001j]
    assert DeepDiff(1-2j,1-3j,significant_digits=2)

def test_zero_extreme_nonfinite_and_subclass():
    """非有限分量和复数子类走同一格式化策略。@return None。"""
    class Amount(complex):
        """业务复数类型。"""
    assert complex(number_to_string(Amount(-0.0,-0.0),2))==0j
    assert complex(number_to_string(1e-15-2e-15j,3,'e'))==0j
    assert 'inf' in number_to_string(complex(1,float('-inf')),2)
    assert 'nan' in number_to_string(complex(1,float('nan')),2)
