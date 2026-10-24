"""时间截断只应用于支持墙钟字段的类型。"""
from datetime import date,datetime,time,timedelta,timezone
from deepdiff import DeepDiff,DeepHash
from deepdiff.helper import datetime_normalize

def test_date_all_precisions_and_subclass():
    """日期及子类不转datetime，也不调用非法replace参数。@return None。"""
    class BusinessDate(date):
        """保持业务日期类型。"""
    for precision in [None,'second','minute','hour','day']:
        value=BusinessDate(2024,1,2)
        assert datetime_normalize(precision,value) is value
        assert DeepDiff(value,BusinessDate(2024,1,2),truncate_datetime=precision)=={}
        assert DeepDiff(value,BusinessDate(2024,1,3),truncate_datetime=precision)

def test_duration_preserved_and_datetime_time_truncated():
    """时长不截断，datetime/time仍走原有墙钟规则。@return None。"""
    assert datetime_normalize('minute',timedelta(seconds=61))==timedelta(seconds=61)
    assert datetime_normalize('minute',datetime(2024,1,2,3,4,5,6)).second==0
    assert datetime_normalize('minute',time(3,4,5))==3*3600+4*60

def test_hash_nested_and_mixed_type_preserve():
    """嵌套哈希与混合date/datetime类型规则保持。@return None。"""
    value=date(2024,1,2)
    assert DeepHash(value,truncate_datetime='minute')[value]==DeepHash(value)[value]
    assert DeepDiff([value],[date(2024,1,3)],truncate_datetime='hour')
    assert 'type_changes' in DeepDiff(value,datetime(2024,1,2),truncate_datetime='day')
