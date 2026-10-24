"Public regression tests for HTML5LIB-O02-DEV; the complete business contract is in materials/HTML5LIB-O02-DEV-contract.md."
from html5lib.filters.lint import Filter
import pytest

def start(name,namespace=None):
    "Support the public regression through start."
    return {'type':'StartTag','name':name,'namespace':namespace,'data':{}}

def test_one_and_nested_unclosed_elements_rejected_after_actual_eof():
    "Verify one and nested unclosed elements rejected after actual eof."
    for tokens in [[start('div')],[start('section'),start('span'),{'type':'EndTag','name':'span','namespace':None}]]:
        with pytest.raises(AssertionError,match='未闭合'):list(Filter(tokens))

def test_lazy_prefix_is_yielded_and_relaxed_mode_does_not_require_closing():
    "Verify lazy prefix is yielded and relaxed mode does not require closing."
    token=start('div');iterator=iter(Filter(iter([token])));assert next(iterator) is token
    with pytest.raises(AssertionError):next(iterator)
    assert list(Filter([token],require_matching_tags=False))==[token]

def test_balanced_foreign_empty_and_unmatched_end_contract():
    "Verify balanced foreign empty and unmatched end contract."
    svg='http://www.w3.org/2000/svg';tokens=[start('svg',svg),{'type':'EndTag','name':'svg','namespace':svg},{'type':'EmptyTag','name':'br','namespace':None,'data':{}}]
    assert list(Filter(tokens))==tokens and list(Filter([]))==[]
    with pytest.raises(AssertionError):list(Filter([{'type':'EndTag','name':'div','namespace':None}]))
