"Public regression tests for PT-MEASURE-DEV; the complete business contract is in materials/PT-MEASURE-DEV-contract.md."
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import portion as P


def test_duration_and_parts():
    "Verify duration and parts."
    windows = P.closedopen(9, 11) | P.closedopen(13, 14)
    assert windows.measure(lambda atom: atom.upper - atom.lower) == 3
    assert len(windows) == 2


def test_discrete_and_decimal():
    "Verify discrete and decimal."
    def count(atom):
        "Support the public regression through count."
        return atom.upper - atom.lower + 1 - (atom.left is P.OPEN) - (atom.right is P.OPEN)
    assert P.closed(1, 3).measure(count) == 3
    assert P.open(1, 3).measure(count) == 1
    assert P.closed(Decimal('1.2'), Decimal('2.7')).measure(lambda atom: atom.upper - atom.lower, start=Decimal(0)) == Decimal('1.5')


def test_empty_and_callback_error():
    "Verify empty and callback error."
    calls = []
    assert P.empty().measure(lambda atom: calls.append(atom), start=timedelta()) == timedelta()
    assert calls == []
    with pytest.raises(ZeroDivisionError):
        P.singleton(1).measure(lambda atom: 1 / 0)
