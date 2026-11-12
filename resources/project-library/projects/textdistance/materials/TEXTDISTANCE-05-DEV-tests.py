"Public regression tests for TEXTDISTANCE-05-DEV; the complete business contract is in materials/TEXTDISTANCE-05-DEV-contract.md."
import unittest
from textdistance.bounded import bounded_levenshtein


def test_exact_boundary_zero_and_units():
    "Verify exact boundary zero and units."
    assert bounded_levenshtein('kitten','sitting',3)==3
    assert bounded_levenshtein('kitten','sitting',2) is None
    assert bounded_levenshtein('same','same',0)==0
    assert bounded_levenshtein('a','b',0) is None
    assert bounded_levenshtein('one two','one three',1,qval=None)==1
    assert bounded_levenshtein('A','a',0,test_func=lambda a,b:a.casefold()==b.casefold())==0


def test_length_gate_and_invalid_threshold():
    "Verify length gate and invalid threshold."
    def forbidden(a,b):
        "Support the public regression through forbidden."
        raise AssertionError('不应执行')
    assert bounded_levenshtein('x'*100000,'',1,test_func=forbidden) is None
    for cutoff in (-1,True,0.5):
        with unittest.TestCase().assertRaises(ValueError):bounded_levenshtein('a','b',cutoff)

