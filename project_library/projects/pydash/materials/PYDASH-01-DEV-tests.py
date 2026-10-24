"""通过实际底层边界验证随机数入口，禁止概率性验收。"""
from unittest.mock import patch
import pydash

def test_single_bound_positive_negative_zero_float_and_chain():
    """单界以零为另一端，链式复用真实入口。@return None。"""
    for bound,expected in ((5,(0,5)),(-3,(-3,0)),(0,(0,0))):
        with patch('pydash.utilities.randint',return_value=9) as draw:
            assert pydash.random(bound)==9;draw.assert_called_once_with(*expected)
    with patch('pydash.utilities.uniform',return_value=0.2) as draw:
        assert pydash.chain(0.5).random().value()==0.2;draw.assert_called_once_with(0,0.5)

def test_no_argument_keyword_stop_and_explicit_reverse_bounds():
    """无参和关键字调用不能被单界修复破坏。@return None。"""
    with patch('pydash.utilities.randint',return_value=0) as draw:
        pydash.random();draw.assert_called_once_with(0,1)
    with patch('pydash.utilities.randint',return_value=0) as draw:
        pydash.random(stop=7);draw.assert_called_once_with(0,7)
    with patch('pydash.utilities.randint',return_value=0) as draw:
        pydash.random(8,1);draw.assert_called_once_with(1,8)

