"""显式度量支持时长和离散计数，不改变len。"""
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import portion as P


def test_duration_and_parts():
    """两个会议空闲窗口总长为3，片段数仍为2。@return None。"""
    windows = P.closedopen(9, 11) | P.closedopen(13, 14)
    assert windows.measure(lambda atom: atom.upper - atom.lower) == 3
    assert len(windows) == 2


def test_discrete_and_decimal():
    """度量协议可以解释开闭边界并保持Decimal类型。@return None。"""
    def count(atom):
        """计算整数原子区间的元素数。@param atom 原子区间。@return 数量。"""
        return atom.upper - atom.lower + 1 - (atom.left is P.OPEN) - (atom.right is P.OPEN)
    assert P.closed(1, 3).measure(count) == 3
    assert P.open(1, 3).measure(count) == 1
    assert P.closed(Decimal('1.2'), Decimal('2.7')).measure(lambda atom: atom.upper - atom.lower, start=Decimal(0)) == Decimal('1.5')


def test_empty_and_callback_error():
    """空集不调用回调，定制度量异常不吞掉。@return None。"""
    calls = []
    assert P.empty().measure(lambda atom: calls.append(atom), start=timedelta()) == timedelta()
    assert calls == []
    with pytest.raises(ZeroDivisionError):
        P.singleton(1).measure(lambda atom: 1 / 0)
