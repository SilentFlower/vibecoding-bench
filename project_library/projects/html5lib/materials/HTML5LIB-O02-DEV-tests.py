"""完整消耗令牌流后必须发现EOF未闭合，宽松模式保持可用。"""
from html5lib.filters.lint import Filter
import pytest

def start(name,namespace=None):
    """构造标准实际walker StartTag。@return Token。"""
    return {'type':'StartTag','name':name,'namespace':namespace,'data':{}}

def test_one_and_nested_unclosed_elements_rejected_after_actual_eof():
    """不是只发现错配EndTag，还要在最后的yield之后检测截断。@return None。"""
    for tokens in [[start('div')],[start('section'),start('span'),{'type':'EndTag','name':'span','namespace':None}]]:
        with pytest.raises(AssertionError,match='未闭合'):list(Filter(tokens))

def test_lazy_prefix_is_yielded_and_relaxed_mode_does_not_require_closing():
    """读取部分仍惰性，真正完整消费才检查EOF，显式宽松允许片段。@return None。"""
    token=start('div');iterator=iter(Filter(iter([token])));assert next(iterator) is token
    with pytest.raises(AssertionError):next(iterator)
    assert list(Filter([token],require_matching_tags=False))==[token]

def test_balanced_foreign_empty_and_unmatched_end_contract():
    """HTML void及SVG命名空间保持，空流合法，孤立关闭统一AssertionError。@return None。"""
    svg='http://www.w3.org/2000/svg';tokens=[start('svg',svg),{'type':'EndTag','name':'svg','namespace':svg},{'type':'EmptyTag','name':'br','namespace':None,'data':{}}]
    assert list(Filter(tokens))==tokens and list(Filter([]))==[]
    with pytest.raises(AssertionError):list(Filter([{'type':'EndTag','name':'div','namespace':None}]))
