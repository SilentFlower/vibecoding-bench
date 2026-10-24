"""公开词排列助手使用真实callable与显式分数方向。"""
import unittest
import textdistance
from textdistance.utils import words_combinations


def test_builtin_distance_similarity_and_plain_callable():
    """不访问内建算法不存在的equality属性。@return None。"""
    assert words_combinations(textdistance.Levenshtein(external=False),'guide archive','archive guide')==0
    assert words_combinations(textdistance.Jaccard(qval=None),'a b','b a',direction='similarity')==1
    assert words_combinations(lambda a,b:abs(len(a)-len(b)),'one','one two')==4
    assert words_combinations(lambda a,b:abs(len(a)-len(b)),'one','one two',truncate=True)==0


def test_duplicate_words_empty_and_budget_preflight():
    """重复词不重复计预算，预算不足不返回伪最优值。@return None。"""
    calls=[]
    assert words_combinations(lambda *items:calls.append(items) or 0,'a a','a',max_permutations=1)==0
    assert len(calls)==1
    assert words_combinations(textdistance.Levenshtein(external=False),'','')==0
    with unittest.TestCase().assertRaises(ValueError):words_combinations(lambda *items:0,'a b c',max_permutations=5)
    with unittest.TestCase().assertRaises(ValueError):words_combinations(lambda *items:0)

