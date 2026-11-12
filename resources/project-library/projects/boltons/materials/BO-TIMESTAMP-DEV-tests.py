"Public regression tests for BO-TIMESTAMP-DEV; the complete business contract is in materials/BO-TIMESTAMP-DEV-contract.md."
from datetime import datetime,tzinfo,timedelta,timezone
import pytest
from boltons.timeutils import dt_to_timestamp

class FalseZone(tzinfo):
    def __bool__(self):
        return False
    def utcoffset(self,value):
        return timedelta(hours=2)
    def dst(self,value):
        return timedelta(0)

def test_falsey_aware_zone_uses_actual_offset():
    value=datetime(1970,1,1,2,tzinfo=FalseZone())
    assert dt_to_timestamp(value)==0

def test_offset_none_retains_original_naive_utc_convention():
    class Naive(tzinfo):
        def utcoffset(self,value):
            return None
    assert dt_to_timestamp(datetime(1970,1,1,tzinfo=Naive()))==0

def test_negative_fractional_epoch_and_input_identity_are_preserved():
    value=datetime(1969,12,31,23,59,59,500000,tzinfo=timezone.utc)
    assert dt_to_timestamp(value)==-0.5 and value.microsecond==500000

def test_offset_errors_propagate():
    class Broken(tzinfo):
        def utcoffset(self,value):
            raise LookupError('synthetic')
    with pytest.raises(LookupError):
        dt_to_timestamp(datetime(2026,1,1,tzinfo=Broken()))
