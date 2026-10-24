"""关键词拆分与合并基于实际Field，不复用作者and规则。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_nested_and_escaped_delimiters():
    """括号和转义保护的逗号不是分隔点。@return None。"""
    from bibtexparser.keywords import SplitKeywords
    source = Library([Entry('article', 'x', [Field('keywords', r'alpha,{beta,{gamma,delta}},escaped\,comma')])])
    result = SplitKeywords().transform(source)
    assert result.entries[0]['keywords'] == ['alpha', '{beta,{gamma,delta}}', r'escaped\,comma']
    assert isinstance(source.entries[0]['keywords'], str)

def test_merge_roundtrip_and_empty_policy():
    """正常双向往返和空项政策可检验。@return None。"""
    from bibtexparser.keywords import SplitKeywords, MergeKeywords
    source = Library([Entry('article', 'x', [Field('keywords', 'a,,{b,c},')])])
    split = SplitKeywords(keep_empty=True).transform(source)
    assert split.entries[0]['keywords'] == ['a', '', '{b,c}', '']
    assert MergeKeywords().transform(split).entries[0]['keywords'] == 'a,,{b,c},'

def test_unbalanced_rejected():
    """不平衡括号拒绝且原对象不变。@return None。"""
    import pytest
    from bibtexparser.keywords import SplitKeywords
    source = Library([Entry('article', 'x', [Field('keywords', 'a,{b,c')])])
    with pytest.raises(ValueError): SplitKeywords().transform(source)
    assert source.entries[0]['keywords'] == 'a,{b,c'
