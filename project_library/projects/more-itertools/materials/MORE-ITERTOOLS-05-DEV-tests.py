"Public regression tests for MORE-ITERTOOLS-05-DEV; the complete business contract is in materials/MORE-ITERTOOLS-05-DEV-contract.md."
from itertools import count,islice
import unittest
from more_itertools import interleave_weighted

def test_two_to_one_prefix_and_early_exhaustion():
    "Verify two to one prefix and early exhaustion."
    assert list(interleave_weighted([1,2,3,4,5],['a','b'],weights=[2,1]))==[1,2,'a',3,4,'b',5]
    assert list(interleave_weighted([],['a','b'],[8],weights=[2,1,3]))==['a',8,'b']

def test_infinite_source_finite_prefix_and_invalid_weights():
    "Verify infinite source finite prefix and invalid weights."
    assert list(islice(interleave_weighted(count(),count(100),weights=[2,1]),6))==[0,1,100,2,3,101]
    for weights in ([0,1],[-1,1],[1], [True,1]):
        with unittest.TestCase().assertRaises((ValueError,TypeError)):list(interleave_weighted([1],[2],weights=weights))

