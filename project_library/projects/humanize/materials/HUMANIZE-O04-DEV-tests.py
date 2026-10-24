"""日期显示围绕显式参考日，不依赖真实墙钟。"""
from datetime import date,datetime,timedelta,timezone
import humanize
import pytest

def test_fixed_reference_both_formatters_and_distant_year():
    """两个API共享参考日及远期年份阈值。@return None。"""
    ref=date(2000,1,2)
    assert humanize.naturalday(date(2000,1,1),when=ref)=='yesterday'
    assert humanize.naturaldate(date(2000,1,3),when=ref)=='tomorrow'
    assert humanize.naturaldate(date(2001,1,2),when=ref)=='Jan 02 2001'
    assert humanize.naturalday('not date',when=ref)=='not date'

def test_aware_reference_converted_into_value_timezone():
    """跨午夜依据目标时区比较，date参考是明确日历日。@return None。"""
    value=datetime(2024,1,2,1,tzinfo=timezone(timedelta(hours=9)))
    ref=datetime(2024,1,1,20,tzinfo=timezone.utc)
    assert humanize.naturalday(value,when=ref)=='today'
    assert humanize.naturalday(value,when=date(2024,1,1))=='tomorrow'

def test_mixed_awareness_and_invalid_reference_rejected():
    """不把不一致显式参考悄悄降级成原字符串。@return None。"""
    with pytest.raises(ValueError):humanize.naturalday(datetime(2024,1,1),when=datetime(2024,1,1,tzinfo=timezone.utc))
    with pytest.raises(TypeError):humanize.naturaldate(date(2024,1,1),when='today')
    assert humanize.naturalday(date.min,when=date.min)=='today'
