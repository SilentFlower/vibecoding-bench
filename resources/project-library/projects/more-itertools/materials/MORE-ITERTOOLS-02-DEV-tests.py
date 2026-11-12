"Public regression tests for MORE-ITERTOOLS-02-DEV; the complete business contract is in materials/MORE-ITERTOOLS-02-DEV-contract.md."
from datetime import datetime,timedelta
import unittest
from more_itertools import sessionize

def test_exact_gap_and_business_payload_identity():
    "Verify exact gap and business payload identity."
    rows=[{'t':0},{'t':3},{'t':6},{'t':10}]
    result=list(sessionize(iter(rows),lambda row:row['t'],3))
    assert result==[rows[:3],rows[3:]] and result[0][0] is rows[0]
    assert list(sessionize([],lambda row:row,0))==[]

def test_cross_day_zero_gap_reverse_and_negative_policy():
    "Verify cross day zero gap reverse and negative policy."
    start=datetime(2024,1,1,23,59)
    assert list(sessionize([start,start+timedelta(minutes=2),start+timedelta(hours=1)],lambda row:row,timedelta(minutes=5)))==[[start,start+timedelta(minutes=2)],[start+timedelta(hours=1)]]
    assert list(sessionize([1,1,2],lambda row:row,0))==[[1,1],[2]]
    for values,gap in (([2,1],1),([1],-1)):
        with unittest.TestCase().assertRaises(ValueError):list(sessionize(values,lambda row:row,gap))

