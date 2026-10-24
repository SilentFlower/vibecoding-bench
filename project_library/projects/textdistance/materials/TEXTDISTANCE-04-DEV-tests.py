"Public regression tests for TEXTDISTANCE-04-DEV; the complete business contract is in materials/TEXTDISTANCE-04-DEV-contract.md."
import unittest
import textdistance
from textdistance.weighted import WeightedLevenshtein


def test_asymmetric_zero_and_callable_costs():
    "Verify asymmetric zero and callable costs."
    algorithm=WeightedLevenshtein(insertion=2,deletion=5,substitution=9)
    assert algorithm('','ab')==4 and algorithm('ab','')==10
    assert algorithm('a','b')==7
    assert WeightedLevenshtein(substitution=0)('a','b')==0
    custom=WeightedLevenshtein(substitution=lambda a,b:0.25 if {a,b}=={'0','O'} else 2)
    assert custom('O1','01')==0.25


def test_units_predicate_and_invalid_costs():
    "Verify units predicate and invalid costs."
    assert WeightedLevenshtein(qval=None)('one two','one three')==1
    assert WeightedLevenshtein(test_func=lambda a,b:a.casefold()==b.casefold())('A','a')==0
    for cost in (-1,float('nan'),float('inf'),True):
        with unittest.TestCase().assertRaises(ValueError):WeightedLevenshtein(insertion=cost)
    with unittest.TestCase().assertRaises(ValueError):WeightedLevenshtein(substitution=lambda a,b:-1)('a','b')

