"Public regression tests for AG-DURATION-DEV; the complete business contract is in materials/AG-DURATION-DEV-contract.md."
from datetime import timedelta
from decimal import Decimal
import warnings
import agate

def table(values):
    return agate.Table([(value,) for value in values], ['duration'], [agate.TimeDelta()])

def test_even_duration_median_and_percentiles():
    data = table([timedelta(seconds=1), timedelta(seconds=3)])
    assert data.aggregate(agate.Median('duration')) == timedelta(seconds=2)
    values = data.aggregate(agate.Percentiles('duration'))
    assert (values[0], values[50], values[100]) == (timedelta(seconds=1), timedelta(seconds=2), timedelta(seconds=3))

def test_odd_and_negative_values():
    data = table([timedelta(seconds=-8), timedelta(seconds=-2), timedelta(seconds=7)])
    assert data.aggregate(agate.Median('duration')) == timedelta(seconds=-2)

def test_microsecond_ties_round_to_even():
    assert table([timedelta(), timedelta(microseconds=1)]).aggregate(agate.Median('duration')) == timedelta()
    assert table([timedelta(microseconds=1), timedelta(microseconds=2)]).aggregate(agate.Median('duration')) == timedelta(microseconds=2)

def test_empty_and_null_values():
    assert table([]).aggregate(agate.Median('duration')) is None
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        assert table([None, timedelta(seconds=9)]).aggregate(agate.Median('duration')) == timedelta(seconds=9)

def test_extreme_midpoints_do_not_overflow():
    assert table([timedelta.max, timedelta.max]).aggregate(agate.Median('duration')) == timedelta.max
    assert table([timedelta.min, timedelta.min]).aggregate(agate.Median('duration')) == timedelta.min

def test_numeric_statistics_are_unchanged():
    data = agate.Table([(1,), (4,)], ['value'], [agate.Number()])
    assert data.aggregate(agate.Median('value')) == Decimal('2.5')
