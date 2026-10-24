"""负微秒跨模板保持符号，重复序列化不修改对象。"""
from pypika import Interval
from pypika.enums import Dialects

def test_signed_microseconds_across_dialects_and_repeat():
    """五类模板均生成负表达式。@return None。"""
    for dialect in (Dialects.POSTGRESQL,Dialects.REDSHIFT,Dialects.VERTICA,Dialects.ORACLE,Dialects.MYSQL):
        value=Interval(microseconds=-7);sql=value.get_sql(dialect=dialect)
        assert '-7' in sql and sql==value.get_sql(dialect=dialect)
        assert value.microseconds==7 and value.is_negative

def test_positive_zero_and_large_values_keep_existing_policy():
    """纯微秒大整数精确，正数和零不添加负号。@return None。"""
    assert '-1' not in Interval(microseconds=1).get_sql()
    assert '0' in Interval(microseconds=0).get_sql()
    assert '-1000000000000000000000' in Interval(microseconds=-(10**21)).get_sql()
    assert Interval(seconds=-1,microseconds=2).get_sql()==Interval(seconds=-1,microseconds=2).get_sql()

