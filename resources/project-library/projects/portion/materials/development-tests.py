"""Public regressions: validate iteration progress on demand and protect callers with a global item limit."""
from datetime import date, timedelta
from itertools import islice
import portion as P
import pytest


def test_checked_rejects_stagnation_and_wrong_direction():
    """Fail finitely for stationary or backward steps and also guard skipped open endpoints. @return None."""
    for interval, step, reverse in ((P.closed(1, 3), 0, False), (P.open(1, 3), lambda x: x, False),
        (P.closed(1, 3), 1, True), (P.closed(1, 3), -1, False)):
        with pytest.raises(ValueError):
            list(P.iterate(interval, step, reverse=reverse, checked=True))


def test_limit_counts_across_disjoint_parts_and_reverse():
    """Apply the item limit to the entire interval stream without resetting it for each segment. @return None."""
    interval = P.closed(0, 2) | P.closed(10, 12)
    assert list(P.iterate(interval, 1, checked=True, max_items=4)) == [0, 1, 2, 10]
    assert list(P.iterate(interval, -1, reverse=True, checked=True, max_items=4)) == [12, 11, 10, 2]


def test_zero_limit_does_not_evaluate_callbacks_and_rejects_bad_limits():
    """Make no business callbacks for a zero-item limit and do not coerce invalid limits to integers. @return None."""
    calls = []
    assert list(P.iterate(P.closed(1, 4), lambda value: calls.append(value),
        base=lambda value: calls.append(value), checked=True, max_items=0)) == []
    assert calls == []
    for limit in (-1, True, 1.5):
        with pytest.raises((ValueError, TypeError)):
            list(P.iterate(P.closed(1, 4), 1, max_items=limit))


def test_date_callable_and_legacy_default_are_preserved():
    """Measure date progress using the actual produced value and preserve the original default behavior. @return None."""
    first = date(2026, 1, 2)
    assert list(P.iterate(P.closed(first, first + timedelta(days=2)),
        lambda value: value + timedelta(days=1), checked=True)) == [first, first + timedelta(days=1), first + timedelta(days=2)]
    assert list(islice(P.iterate(P.closed(1, 4), 0), 3)) == [1, 1, 1]
