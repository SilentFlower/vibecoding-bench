"Public regression tests for BIBTEXPARSER-O01-DEV; the complete business contract is in materials/BIBTEXPARSER-O01-DEV-contract.md."
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_parent_fields_and_override():
    "Verify parent fields and override."
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    source = Library([Entry('proceedings', 'P', [Field('title', 'Book'), Field('year', '2026')]), Entry('inproceedings', 'C', [Field('title', 'Paper'), Field('crossref', 'P')])])
    result = ResolveCrossrefMiddleware().transform(source)
    assert result.entries_dict['C']['booktitle'] == 'Book'
    assert result.entries_dict['C']['year'] == '2026' and result.entries_dict['C']['title'] == 'Paper'
    assert 'year' not in source.entries_dict['C'].fields_dict

def test_nested_and_provenance():
    "Verify nested and provenance."
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    source = Library([Entry('book', 'A', [Field('year', '2025')]), Entry('book', 'B', [Field('crossref', 'A')]), Entry('article', 'C', [Field('crossref', 'B')])])
    result = ResolveCrossrefMiddleware().transform(source)
    assert result.entries_dict['C']['year'] == '2025'
    assert result.entries_dict['C'].parser_metadata['crossref_sources']['year'] == 'B'

def test_missing_and_cycle():
    "Verify missing and cycle."
    import pytest
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    missing = Library([Entry('article', 'C', [Field('crossref', 'absent')])])
    with pytest.raises(ValueError): ResolveCrossrefMiddleware().transform(missing)
    assert ResolveCrossrefMiddleware(missing='ignore').transform(missing).entries[0].key == 'C'
    cycle = Library([Entry('book', 'A', [Field('crossref', 'B')]), Entry('book', 'B', [Field('crossref', 'A')])])
    with pytest.raises(ValueError): ResolveCrossrefMiddleware().transform(cycle)
