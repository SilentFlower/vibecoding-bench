"Public regression tests for HTML5LIB-O01-DEV; the complete business contract is in materials/HTML5LIB-O01-DEV-contract.md."
from html5lib.filters.lint import Filter
import pytest

def test_bad_public_and_system_ids_fail_independently_of_valid_name():
    "Verify bad public and system ids fail independently of valid name."
    for key in ['publicId','systemId']:
        for value in [42,b'bytes',{},[]]:
            token={'type':'Doctype','name':'html','publicId':None,'systemId':None};token[key]=value
            with pytest.raises(AssertionError):list(Filter([token]))

def test_optional_name_does_not_reject_valid_text_identifiers():
    "Verify optional name does not reject valid text identifiers."
    token={'type':'Doctype','name':None,'publicId':'public','systemId':'system'}
    assert list(Filter([token]))==[token] and list(Filter([token]))[0] is token

def test_real_tree_walker_doctype_and_other_token_validation_stay_valid():
    "Verify real tree walker doctype and other token validation stay valid."
    import html5lib
    tree=html5lib.parse('<!doctype html><p>text',treebuilder='dom')
    tokens=list(html5lib.getTreeWalker('dom')(tree));assert list(Filter(tokens))==tokens
    with pytest.raises(AssertionError):list(Filter([{'type':'Comment','data':42}]))
