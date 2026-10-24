"""公开的固定参考时刻回归。"""
from datetime import date, datetime, timezone
import pickle
import pytest
import agate

def test_relative_date_uses_fixed_reference():
    field = agate.Date(reference_datetime=datetime(2024, 2, 28, 12), locale='en_US')
    assert field.cast('tomorrow') == date(2024, 2, 29)

def test_relative_datetime_uses_fixed_reference():
    field = agate.DateTime(reference_datetime=datetime(2024, 2, 28, 12), locale='en_US')
    assert field.cast('tomorrow at 9am') == datetime(2024, 2, 29, 9)

def test_reference_survives_serialization():
    field = agate.Date(reference_datetime=datetime(2025, 12, 31, 23), locale='en_US')
    assert pickle.loads(pickle.dumps(field)).cast('tomorrow') == date(2026, 1, 1)

def test_formats_and_absolute_values_keep_their_priority():
    field = agate.Date(date_format='%d/%m/%Y', reference_datetime=datetime(2024, 1, 1))
    assert field.cast('16/07/2030') == date(2030, 7, 16)
    assert agate.DateTime(reference_datetime=datetime(2024, 1, 1)).cast('2030-07-16T10:20:30') == datetime(2030, 7, 16, 10, 20, 30)

def test_invalid_reference_types_are_rejected():
    for invalid in (date(2024, 1, 1), '2024-01-01', datetime(2024, 1, 1, tzinfo=timezone.utc)):
        with pytest.raises(TypeError):
            agate.Date(reference_datetime=invalid)
        with pytest.raises(TypeError):
            agate.DateTime(reference_datetime=invalid)

def test_nulls_and_existing_typed_values_are_preserved():
    field = agate.Date(reference_datetime=datetime(2024, 1, 1))
    value = date(2040, 5, 6)
    assert field.cast(None) is None and field.cast(value) is value
