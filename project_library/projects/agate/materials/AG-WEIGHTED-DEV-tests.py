"""公开销量加权分析回归。"""
from decimal import Decimal
import agate
import pytest

def table(rows):
    return agate.Table(rows, ['price', 'units'], [agate.Number(), agate.Number()])

def test_weighted_mean_uses_quantity_not_row_count():
    assert table([(2, 1), (6, 3)]).aggregate(agate.WeightedMean('price', 'units')) == Decimal(5)

def test_population_variance_has_the_documented_denominator():
    assert table([(2, 1), (6, 3)]).aggregate(agate.WeightedVariance('price', 'units')) == Decimal(3)

def test_null_pairs_and_zero_weights_do_not_contribute():
    data = table([(None, 100), (99, None), (2, 1), (6, 3), (900, 0)])
    assert data.aggregate(agate.WeightedMean('price', 'units')) == Decimal(5)

def test_empty_or_zero_weight_returns_none():
    assert table([]).aggregate(agate.WeightedMean('price', 'units')) is None
    assert table([(1, 0)]).aggregate(agate.WeightedVariance('price', 'units')) is None

def test_negative_weights_are_rejected_before_calculation():
    with pytest.raises(ValueError):
        table([(1, -1), (2, 3)]).aggregate(agate.WeightedMean('price', 'units'))

def test_decimal_precision_and_original_mean():
    data = table([('1000000000000000', 1), ('1000000000000001', 1)])
    assert data.aggregate(agate.WeightedVariance('price', 'units')) == Decimal('0.25')
    assert table([(2, 1), (6, 3)]).aggregate(agate.Mean('price')) == Decimal(4)
