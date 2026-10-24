"""公开分组前后记录回归。"""
from decimal import Decimal
import agate
import pytest

def table():
    return agate.Table([('a', 10), ('b', 20), ('a', 30), ('b', 40)], ['client', 'value'], [agate.Text(), agate.Number()])

def test_partition_lag_respects_interleaved_original_rows():
    data = table().compute([('previous', agate.Lag('value', partition_by='client'))])
    assert data.columns['previous'].values() == (None, None, Decimal(10), Decimal(20))

def test_partition_lead_and_cast_default():
    data = table().compute([('next', agate.Lead('value', default='99', partition_by=['client']))])
    assert data.columns['next'].values() == (Decimal(30), Decimal(40), Decimal(99), Decimal(99))

def test_zero_and_large_offsets_keep_type_and_length():
    source = table()
    data = source.compute([('same', agate.Lag('value', 0)), ('missing', agate.Lead('value', 100))])
    assert data.columns['same'].values() == source.columns['value'].values()
    assert data.columns['missing'].values() == (None,) * 4
    assert isinstance(data.columns['same'].data_type, agate.Number)

def test_invalid_offset_is_not_silently_coerced():
    for value in (-1, 1.5, True):
        with pytest.raises(ValueError):
            agate.Lag('value', value)

def test_default_and_partition_names_are_checked():
    with pytest.raises(agate.CastError):
        table().compute([('x', agate.Lag('value', default='invalid'))])
    with pytest.raises(KeyError):
        table().compute([('x', agate.Lag('value', partition_by='unknown'))])

def test_original_table_is_not_mutated():
    source = table()
    source.compute([('x', agate.Lead('value'))])
    assert source.column_names == ('client', 'value')
