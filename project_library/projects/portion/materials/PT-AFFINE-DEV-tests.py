"""仿射像正确处理负比例、零比例和无穷。"""
from decimal import Decimal
import pytest
import portion as P


def test_negative_and_translation():
    """负比例交换开闭端点，多片段平移保持空隙。@return None。"""
    assert P.closedopen(1, 3).affine(-2, 1) == P.openclosed(-5, -1)
    assert (P.closed(1, 2) | P.closed(5, 6)).translate(3) == P.closed(4, 5) | P.closed(8, 9)


def test_zero_and_infinity():
    """非空零比例映为单点，空集仍空，无穷方向正确。@return None。"""
    assert P.open(1, 3).affine(0, 7) == P.singleton(7)
    assert P.empty().affine(0, 7).empty
    assert P.open(0, P.inf).affine(-1) == P.open(-P.inf, 0)


def test_decimal_and_discrete_rejection():
    """保留Decimal并显式拒绝不能表达的离散点像。@return None。"""
    assert P.closed(Decimal('1'), Decimal('2')).affine(Decimal('2'), Decimal('.5')) == P.closed(Decimal('2.5'), Decimal('4.5'))
    class Integers(P.AbstractDiscreteInterval):
        """整数域。"""
        _step = 1
    with pytest.raises(TypeError):
        P.create_api(Integers).closed(1, 3).affine(2)
