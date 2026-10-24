"""tail零项请求不读取流，也不返回全部序列。"""
import pytest
from toolz import tail


def test_zero_keeps_slice_type():
    """列表、元组和字符串返回各自空类型。@return None。"""
    assert tail(0, [1, 2]) == []
    assert tail(0, (1, 2)) == ()
    assert tail(0, 'ab') == ''


def test_zero_does_not_consume():
    """一次性流在零项请求后仍保留首项。@return None。"""
    source = iter([10, 20])
    assert tail(0, source) == ()
    assert next(source) == 10


def test_negative_and_positive():
    """负数统一拒绝，正常末尾选择保持。@return None。"""
    for source in ([1, 2], iter([1, 2])):
        with pytest.raises(ValueError):
            tail(-1, source)
    assert tail(2, [1, 2, 3]) == [2, 3]
