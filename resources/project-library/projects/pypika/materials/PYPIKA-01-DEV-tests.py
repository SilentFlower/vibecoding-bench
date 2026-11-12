"Public regression tests for PYPIKA-01-DEV; the complete business contract is in materials/PYPIKA-01-DEV-contract.md."
from pypika import Interval
from pypika.enums import Dialects

def test_signed_microseconds_across_dialects_and_repeat():
    "Verify signed microseconds across dialects and repeat."
    for dialect in (Dialects.POSTGRESQL,Dialects.REDSHIFT,Dialects.VERTICA,Dialects.ORACLE,Dialects.MYSQL):
        value=Interval(microseconds=-7);sql=value.get_sql(dialect=dialect)
        assert '-7' in sql and sql==value.get_sql(dialect=dialect)
        assert value.microseconds==7 and value.is_negative

def test_positive_zero_and_large_values_keep_existing_policy():
    "Verify positive zero and large values keep existing policy."
    assert '-1' not in Interval(microseconds=1).get_sql()
    assert '0' in Interval(microseconds=0).get_sql()
    assert '-1000000000000000000000' in Interval(microseconds=-(10**21)).get_sql()
    assert Interval(seconds=-1,microseconds=2).get_sql()==Interval(seconds=-1,microseconds=2).get_sql()

