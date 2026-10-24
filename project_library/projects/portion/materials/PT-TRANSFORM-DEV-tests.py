"Public regression tests for PT-TRANSFORM-DEV; the complete business contract is in materials/PT-TRANSFORM-DEV-contract.md."
import portion as P


def test_transform_and_original():
    "Verify transform and original."
    original = P.IntervalDict([(P.closedopen(0, 2), 10), (P.closedopen(3, 5), 20)])
    result = original.transform_values(lambda value: value * 2)
    assert result[1] == 20 and result[4] == 40
    assert result.domain() == original.domain()
    assert original[1] == 10


def test_drop_and_none():
    "Verify drop and none."
    original = P.IntervalDict([(P.closedopen(0, 2), 1), (P.closedopen(3, 5), 2)])
    result = original.transform_values(lambda value: None if value == 1 else P.IntervalDict.DROP)
    assert result[1] is None and 4 not in result


def test_composite_callback_and_merge():
    "Verify composite callback and merge."
    original = P.IntervalDict([(P.closedopen(0, 1), 1), (P.closedopen(2, 3), 1), (P.closedopen(4, 5), 2)])
    seen = []
    result = original.transform_values(lambda value, interval: seen.append(interval) or [0], pass_interval=True)
    assert len(seen) == 2 and len(seen[0]) == 2
    assert len(result) == 1 and result.domain() == original.domain()
