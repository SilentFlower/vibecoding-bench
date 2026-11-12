"""Public regressions: an internal partition sentinel must not consume business strings."""
from itertools import count, islice
from toolz import partition, partition_all


def test_exact_old_marker_in_complete_and_partial_batches():
    """Preserve the old sentinel literal wherever it appears in real data. @return None."""
    marker = '__no__pad__'
    assert list(partition_all(2, iter([1, marker]))) == [(1, marker)]
    assert list(partition_all(2, iter([marker, 2, marker]))) == [(marker, 2), (marker,)]


def test_explicit_marker_string_is_real_padding():
    """An explicitly supplied string with the same value still acts as the padding value. @return None."""
    assert list(partition(3, [1], pad='__no__pad__')) == [(1, '__no__pad__', '__no__pad__')]


def test_default_padding_and_lazy_stream_remain_compatible():
    """Preserve default remainder dropping, finite prefixes of infinite streams, and the original batch type. @return None."""
    assert list(partition(2, [1, 2, 3])) == [(1, 2)]
    assert list(islice(partition_all(2, count()), 2)) == [(0, 1), (2, 3)]


def test_none_and_empty_inputs():
    """Treat null as an ordinary item and produce no batches for empty input. @return None."""
    assert list(partition_all(3, [None, '__no__pad__', None])) == [(None, '__no__pad__', None)]
    assert list(partition_all(2, [])) == []
