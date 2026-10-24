"""交叉引用继承需要真实条目对象和原库隔离。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_parent_fields_and_override():
    """子标题保持，继承论文集名和年份。@return None。"""
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    source = Library([Entry('proceedings', 'P', [Field('title', 'Book'), Field('year', '2026')]), Entry('inproceedings', 'C', [Field('title', 'Paper'), Field('crossref', 'P')])])
    result = ResolveCrossrefMiddleware().transform(source)
    assert result.entries_dict['C']['booktitle'] == 'Book'
    assert result.entries_dict['C']['year'] == '2026' and result.entries_dict['C']['title'] == 'Paper'
    assert 'year' not in source.entries_dict['C'].fields_dict

def test_nested_and_provenance():
    """多级父项按序解析并记录字段来源。@return None。"""
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    source = Library([Entry('book', 'A', [Field('year', '2025')]), Entry('book', 'B', [Field('crossref', 'A')]), Entry('article', 'C', [Field('crossref', 'B')])])
    result = ResolveCrossrefMiddleware().transform(source)
    assert result.entries_dict['C']['year'] == '2025'
    assert result.entries_dict['C'].parser_metadata['crossref_sources']['year'] == 'B'

def test_missing_and_cycle():
    """缺父和引用环明确失败，忽略政策可选择。@return None。"""
    import pytest
    from bibtexparser.crossref import ResolveCrossrefMiddleware
    missing = Library([Entry('article', 'C', [Field('crossref', 'absent')])])
    with pytest.raises(ValueError): ResolveCrossrefMiddleware().transform(missing)
    assert ResolveCrossrefMiddleware(missing='ignore').transform(missing).entries[0].key == 'C'
    cycle = Library([Entry('book', 'A', [Field('crossref', 'B')]), Entry('book', 'B', [Field('crossref', 'A')])])
    with pytest.raises(ValueError): ResolveCrossrefMiddleware().transform(cycle)
