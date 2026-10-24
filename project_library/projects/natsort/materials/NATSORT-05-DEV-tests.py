"""已排序记录可按相同自然策略查询等价区间。"""
import unittest
from natsort.search import NaturalSortedIndex


def test_equal_keys_and_ranges():
    """02和2的左右界正确，返回原项。@return None。"""
    index=NaturalSortedIndex(['x1','x2','x02','x3','x10'])
    assert index.rank('x2')==1 and index.rank('x2','right')==3 and index.count('x2')==2
    assert index.between('x2','x3')==['x2','x02','x3']
    assert index.between('x2','x3',include_start=False)==['x3']


def test_reverse_records_and_snapshot():
    """降序索引保留记录且不依赖调用者列表后续重排。@return None。"""
    records=[{'v':'x10'},{'v':'x3'},{'v':'x2'}]
    index=NaturalSortedIndex(records,key=lambda row:row['v'],reverse=True)
    records.reverse()
    assert index.rank('x3')==1 and index.between('x2','x3')==[{'v':'x3'},{'v':'x2'}]
    assert len(index)==3


def test_empty_and_disorder_rejection():
    """不把字典序数组误当自然序，也不静默排序。@return None。"""
    assert NaturalSortedIndex([]).between()==[]
    with unittest.TestCase().assertRaises(ValueError):NaturalSortedIndex(['x10','x2'])
    with unittest.TestCase().assertRaises(ValueError):NaturalSortedIndex(['x1']).rank('x2','middle')

