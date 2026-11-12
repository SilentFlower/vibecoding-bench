"Public regression tests for PT-SPLIT-DEV; the complete business contract is in materials/PT-SPLIT-DEV-contract.md."
import portion as P


def test_right_owned_partition():
    "Verify right owned partition."
    original = P.closedopen(9, 13)
    parts = original.split([12, 10, 10])
    assert parts == (P.closedopen(9, 10), P.closedopen(10, 12), P.closedopen(12, 13))
    assert P.Interval(*parts) == original
    assert all((one & two).empty for index, one in enumerate(parts) for two in parts[index + 1:])


def test_left_ownership_and_open_bounds():
    "Verify left ownership and open bounds."
    assert P.open(0, 3).split([1], ownership='left') == (P.openclosed(0, 1), P.open(1, 3))


def test_disjoint_empty_and_singleton():
    "Verify disjoint empty and singleton."
    original = P.closed(0, 1) | P.closed(3, 4)
    assert original.split([-1, 2, 5]) == (P.closed(0, 1), P.closed(3, 4))
    assert P.empty().split([0]) == ()
    assert P.singleton(2).split([2]) == (P.singleton(2),)
