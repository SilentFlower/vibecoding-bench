"""切点分区不自动归并，端点所有权明确。"""
import portion as P


def test_right_owned_partition():
    """会议窗口按两个切点拆成三个不交叠分区。@return None。"""
    original = P.closedopen(9, 13)
    parts = original.split([12, 10, 10])
    assert parts == (P.closedopen(9, 10), P.closedopen(10, 12), P.closedopen(12, 13))
    assert P.Interval(*parts) == original
    assert all((one & two).empty for index, one in enumerate(parts) for two in parts[index + 1:])


def test_left_ownership_and_open_bounds():
    """左归属不丢掉开边界。@return None。"""
    assert P.open(0, 3).split([1], ownership='left') == (P.openclosed(0, 1), P.open(1, 3))


def test_disjoint_empty_and_singleton():
    """域外切点忽略，空集与单点保持。@return None。"""
    original = P.closed(0, 1) | P.closed(3, 4)
    assert original.split([-1, 2, 5]) == (P.closed(0, 1), P.closed(3, 4))
    assert P.empty().split([0]) == ()
    assert P.singleton(2).split([2]) == (P.singleton(2),)
