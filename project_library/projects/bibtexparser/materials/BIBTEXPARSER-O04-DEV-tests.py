"Public regression tests for BIBTEXPARSER-O04-DEV; the complete business contract is in materials/BIBTEXPARSER-O04-DEV-contract.md."
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_nested_and_escaped_delimiters():
    "Verify nested and escaped delimiters."
    from bibtexparser.keywords import SplitKeywords
    source = Library([Entry('article', 'x', [Field('keywords', r'alpha,{beta,{gamma,delta}},escaped\,comma')])])
    result = SplitKeywords().transform(source)
    assert result.entries[0]['keywords'] == ['alpha', '{beta,{gamma,delta}}', r'escaped\,comma']
    assert isinstance(source.entries[0]['keywords'], str)

def test_merge_roundtrip_and_empty_policy():
    "Verify merge roundtrip and empty policy."
    from bibtexparser.keywords import SplitKeywords, MergeKeywords
    source = Library([Entry('article', 'x', [Field('keywords', 'a,,{b,c},')])])
    split = SplitKeywords(keep_empty=True).transform(source)
    assert split.entries[0]['keywords'] == ['a', '', '{b,c}', '']
    assert MergeKeywords().transform(split).entries[0]['keywords'] == 'a,,{b,c},'

def test_unbalanced_rejected():
    "Verify unbalanced rejected."
    import pytest
    from bibtexparser.keywords import SplitKeywords
    source = Library([Entry('article', 'x', [Field('keywords', 'a,{b,c')])])
    with pytest.raises(ValueError): SplitKeywords().transform(source)
    assert source.entries[0]['keywords'] == 'a,{b,c'
