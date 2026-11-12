"Public regression tests for NATSORT-05-DEV; the complete business contract is in materials/NATSORT-05-DEV-contract.md."
import unittest
from natsort.search import NaturalSortedIndex


def test_equal_keys_and_ranges():
    "Verify equal keys and ranges."
    index=NaturalSortedIndex(['x1','x2','x02','x3','x10'])
    assert index.rank('x2')==1 and index.rank('x2','right')==3 and index.count('x2')==2
    assert index.between('x2','x3')==['x2','x02','x3']
    assert index.between('x2','x3',include_start=False)==['x3']


def test_reverse_records_and_snapshot():
    "Verify reverse records and snapshot."
    records=[{'v':'x10'},{'v':'x3'},{'v':'x2'}]
    index=NaturalSortedIndex(records,key=lambda row:row['v'],reverse=True)
    records.reverse()
    assert index.rank('x3')==1 and index.between('x2','x3')==[{'v':'x3'},{'v':'x2'}]
    assert len(index)==3


def test_empty_and_disorder_rejection():
    "Verify empty and disorder rejection."
    assert NaturalSortedIndex([]).between()==[]
    with unittest.TestCase().assertRaises(ValueError):NaturalSortedIndex(['x10','x2'])
    with unittest.TestCase().assertRaises(ValueError):NaturalSortedIndex(['x1']).rank('x2','middle')

