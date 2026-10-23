"""公开回归：业务字符串不能被分批内部缺失标记吞掉。"""
from itertools import count, islice
from toolz import partition, partition_all


def test_exact_old_marker_in_complete_and_partial_batches():
    """旧标记字面量出现在真实数据任意位置都应保留。@return None。"""
    marker = '__no__pad__'
    assert list(partition_all(2, iter([1, marker]))) == [(1, marker)]
    assert list(partition_all(2, iter([marker, 2, marker]))) == [(marker, 2), (marker,)]


def test_explicit_marker_string_is_real_padding():
    """显式传入同值字符串仍表示填充值。@return None。"""
    assert list(partition(3, [1], pad='__no__pad__')) == [(1, '__no__pad__', '__no__pad__')]


def test_default_padding_and_lazy_stream_remain_compatible():
    """默认丢残批、无限流有限前缀和原批次类型保持。@return None。"""
    assert list(partition(2, [1, 2, 3])) == [(1, 2)]
    assert list(islice(partition_all(2, count()), 2)) == [(0, 1), (2, 3)]


def test_none_and_empty_inputs():
    """空值是普通元素，空输入不制造批次。@return None。"""
    assert list(partition_all(3, [None, '__no__pad__', None])) == [(None, '__no__pad__', None)]
    assert list(partition_all(2, [])) == []
