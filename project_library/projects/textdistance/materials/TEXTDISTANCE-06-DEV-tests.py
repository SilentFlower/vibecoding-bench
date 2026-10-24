"""候选检索保持真实身份与稳定并列，分数方向明确。"""
import unittest
import textdistance
from textdistance.retrieval import extract


def test_distance_similarity_duplicate_identity_and_ties():
    """不比较不可排序ID，不把重复值静默去重。@return None。"""
    choices=[({'id':1},'cot'),({'id':2},'cat'),({'id':3},'cut'),({'id':4},'cot')]
    result=extract('cat',iter(choices),textdistance.Levenshtein(external=False),k=3,threshold=1)
    assert [item.index for item in result]==[1,0,2]
    result=extract('a b',[(1,'a b'),(2,'a c'),(3,'x')],textdistance.Jaccard(qval=None),k=2,direction='similarity')
    assert [item.id for item in result]==[1,2] and result[0].score==1


def test_no_consumption_zero_budget_and_bad_score():
    """零K不消费，预算不足及坏评分不能变成部分成功。@return None。"""
    def forbidden():
        """模拟不应消费的数据源。@return 不返回。"""
        raise AssertionError('不应消费')
        yield None
    assert extract('a',forbidden(),lambda a,b:0,k=0)==[]
    with unittest.TestCase().assertRaises(ValueError):extract('a',[(1,'a'),(2,'b')],lambda a,b:0,max_candidates=1)
    with unittest.TestCase().assertRaises(ValueError):extract('a',[(1,'a')],lambda a,b:float('nan'))

