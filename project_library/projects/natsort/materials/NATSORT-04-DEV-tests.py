"Public regression tests for NATSORT-04-DEV; the complete business contract is in materials/NATSORT-04-DEV-contract.md."
import itertools
import unittest
from natsort.merge import merge_sorted


def test_merge_and_equal_key_stream_order():
    "Verify merge and equal key stream order."
    assert list(merge_sorted(['x1','x10'],['x2','x20']))==['x1','x2','x10','x20']
    assert list(merge_sorted(['x2'],['x02']))==['x2','x02']
    assert list(merge_sorted(['x10','x2'],['x9','x1'],reverse=True))==['x10','x9','x2','x1']


def test_strict_and_lazy_input():
    "Verify strict and lazy input."
    with unittest.TestCase().assertRaises(ValueError):list(merge_sorted(['x2','x1']))
    seen=[]
    def numbers():
        "Support the public regression through numbers."
        for i in itertools.count():
            seen.append(i)
            yield 'n'+str(i)
    result=merge_sorted(numbers())
    assert list(itertools.islice(result,3))==['n0','n1','n2']
    result.close()
    assert len(seen)<=4


def test_records_and_empty_streams():
    "Verify records and empty streams."
    a=[{'name':'a2','id':1}];b=[{'name':'a10','id':2}]
    assert list(merge_sorted([],a,b,key=lambda row:row['name']))==a+b
    assert list(merge_sorted())==[]

