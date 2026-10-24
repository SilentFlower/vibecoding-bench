"""Doctype lint必须检查每个实际字段，而非错误复用name类型。"""
from html5lib.filters.lint import Filter
import pytest

def test_bad_public_and_system_ids_fail_independently_of_valid_name():
    """name合法不能放行整数/字节/容器ID字段。@return None。"""
    for key in ['publicId','systemId']:
        for value in [42,b'bytes',{},[]]:
            token={'type':'Doctype','name':'html','publicId':None,'systemId':None};token[key]=value
            with pytest.raises(AssertionError):list(Filter([token]))

def test_optional_name_does_not_reject_valid_text_identifiers():
    """name可为None，独立文本public/system仍合法且对象身份保持。@return None。"""
    token={'type':'Doctype','name':None,'publicId':'public','systemId':'system'}
    assert list(Filter([token]))==[token] and list(Filter([token]))[0] is token

def test_real_tree_walker_doctype_and_other_token_validation_stay_valid():
    """真实DOM walker声明通过，其他无效注释仍被原lint拒绝。@return None。"""
    import html5lib
    tree=html5lib.parse('<!doctype html><p>text',treebuilder='dom')
    tokens=list(html5lib.getTreeWalker('dom')(tree));assert list(Filter(tokens))==tokens
    with pytest.raises(AssertionError):list(Filter([{'type':'Comment','data':42}]))
