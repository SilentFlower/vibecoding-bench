"Public regression tests for TEXTDISTANCE-03-DEV; the complete business contract is in materials/TEXTDISTANCE-03-DEV-contract.md."
import unittest
import textdistance
from textdistance.utils import words_combinations


def test_builtin_distance_similarity_and_plain_callable():
    "Verify builtin distance similarity and plain callable."
    assert words_combinations(textdistance.Levenshtein(external=False),'guide archive','archive guide')==0
    assert words_combinations(textdistance.Jaccard(qval=None),'a b','b a',direction='similarity')==1
    assert words_combinations(lambda a,b:abs(len(a)-len(b)),'one','one two')==4
    assert words_combinations(lambda a,b:abs(len(a)-len(b)),'one','one two',truncate=True)==0


def test_duplicate_words_empty_and_budget_preflight():
    "Verify duplicate words empty and budget preflight."
    calls=[]
    assert words_combinations(lambda *items:calls.append(items) or 0,'a a','a',max_permutations=1)==0
    assert len(calls)==1
    assert words_combinations(textdistance.Levenshtein(external=False),'','')==0
    with unittest.TestCase().assertRaises(ValueError):words_combinations(lambda *items:0,'a b c',max_permutations=5)
    with unittest.TestCase().assertRaises(ValueError):words_combinations(lambda *items:0)

