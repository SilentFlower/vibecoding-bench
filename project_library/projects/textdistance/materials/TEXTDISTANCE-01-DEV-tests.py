"""最长公共子序列的自定义相等谓词不能只在多序列路径生效。"""
import textdistance


def test_pair_and_multi_sequence_keep_first_spelling():
    """大小写不敏感比较统一使用谓词，返回首输入原字符。@return None。"""
    same=lambda *chars:len({char.casefold() for char in chars})==1
    algorithm=textdistance.LCSSeq(test_func=same,external=False)
    assert algorithm('AbC','aBc')=='AbC'
    assert algorithm('AbC','aBc','ABC')=='AbC'
    assert algorithm.similarity('A','a')==1


def test_nontransitive_predicate_is_not_replaced_by_hash_key():
    """按明确的逐对谓词求解，不能假设等价类或强制小写。@return None。"""
    algorithm=textdistance.LCSSeq(test_func=lambda a,b:abs(ord(a)-ord(b))<=1,external=False)
    assert algorithm('ab','bc')=='ab'
    assert algorithm('a','c')==''
    assert textdistance.LCSSeq(external=False)('DIXON','DICKSONX')=='DION'

