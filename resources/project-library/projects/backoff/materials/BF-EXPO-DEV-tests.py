"Public regression tests for BF-EXPO-DEV; the complete business contract is in materials/BF-EXPO-DEV-contract.md."
from itertools import islice
import pytest
import backoff


def test_overflow_caps():
    "Verify overflow caps."
    values = backoff.expo(base=1e308, factor=1e-308, max_value=5)
    next(values)
    assert list(islice(values, 5)) == [1e-308, 0.9999999999999999, 5, 5, 5]


def test_intermediate_overflow_below_cap():
    "Verify intermediate overflow below cap."
    values = backoff.expo(base=1e200, factor=1e-300, max_value=1e300)
    next(values)
    assert next(values) == 1e-300
    assert next(values) == 1e-100
    assert next(values) == pytest.approx(1e100)
    assert next(values) == pytest.approx(1e300)
    assert next(values) == 1e300


def test_normal_zero_and_decay():
    "Verify normal zero and decay."
    values = backoff.expo(base=1e308, factor=0, max_value=5)
    next(values)
    assert list(islice(values, 5)) == [0] * 5
    values = backoff.expo(base=0.5, max_value=2)
    next(values)
    assert list(islice(values, 3)) == [1, 0.5, 0.25]
