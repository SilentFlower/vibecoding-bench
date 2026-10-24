"Public regression tests for TEXTDISTANCE-06-DEV; the complete business contract is in materials/TEXTDISTANCE-06-DEV-contract.md."
import unittest
import textdistance
from textdistance.retrieval import extract


def test_distance_similarity_duplicate_identity_and_ties():
    "Verify distance similarity duplicate identity and ties."
    choices=[({'id':1},'cot'),({'id':2},'cat'),({'id':3},'cut'),({'id':4},'cot')]
    result=extract('cat',iter(choices),textdistance.Levenshtein(external=False),k=3,threshold=1)
    assert [item.index for item in result]==[1,0,2]
    result=extract('a b',[(1,'a b'),(2,'a c'),(3,'x')],textdistance.Jaccard(qval=None),k=2,direction='similarity')
    assert [item.id for item in result]==[1,2] and result[0].score==1


def test_no_consumption_zero_budget_and_bad_score():
    "Verify no consumption zero budget and bad score."
    def forbidden():
        "Support the public regression through forbidden."
        raise AssertionError('不应消费')
        yield None
    assert extract('a',forbidden(),lambda a,b:0,k=0)==[]
    with unittest.TestCase().assertRaises(ValueError):extract('a',[(1,'a'),(2,'b')],lambda a,b:0,max_candidates=1)
    with unittest.TestCase().assertRaises(ValueError):extract('a',[(1,'a')],lambda a,b:float('nan'))

