"Public regression tests for TZ-TAIL-DEV; the complete business contract is in materials/TZ-TAIL-DEV-contract.md."
import pytest
from toolz import tail


def test_zero_keeps_slice_type():
    "Verify zero keeps slice type."
    assert tail(0, [1, 2]) == []
    assert tail(0, (1, 2)) == ()
    assert tail(0, 'ab') == ''


def test_zero_does_not_consume():
    "Verify zero does not consume."
    source = iter([10, 20])
    assert tail(0, source) == ()
    assert next(source) == 10


def test_negative_and_positive():
    "Verify negative and positive."
    for source in ([1, 2], iter([1, 2])):
        with pytest.raises(ValueError):
            tail(-1, source)
    assert tail(2, [1, 2, 3]) == [2, 3]
