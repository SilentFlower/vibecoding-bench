"""近似合并显式报告新增集合元素。"""
from datetime import date, timedelta
import pytest
import portion as P


def test_bridge_and_gap_report():
    """小空隙填补且返回真实开区间缺口。@return None。"""
    source = P.closed(1, 2) | P.closed(2.1, 3)
    result, gaps = source.coalesce(0.2, report=True)
    assert result == P.closed(1, 3)
    assert gaps == (P.open(2, 2.1),)
    assert len(source) == 2


def test_open_single_point_gap():
    """零距离也可填补两侧都开放造成的缺失单点。@return None。"""
    result, gaps = (P.open(0, 1) | P.open(1, 2)).coalesce(0, report=True)
    assert result == P.open(0, 2) and gaps == (P.singleton(1),)


def test_date_metric_and_negative():
    """日期时长及非法容差明确。@return None。"""
    source = P.closed(date(2026, 1, 1), date(2026, 1, 2)) | P.closed(date(2026, 1, 4), date(2026, 1, 5))
    assert len(source.coalesce(timedelta(days=2))) == 1
    with pytest.raises(ValueError):
        source.coalesce(timedelta(days=-1))
