"""书目校验报告真实缺失字段并保留原始内容。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_article_required_fields():
    """文章缺期刊和作者可同时定位。@return None。"""
    from bibtexparser.validation import validate_entries
    source = Library([Entry('article', 'x', [Field('title', 'Paper'), Field('year', '2026')])])
    diagnostics = validate_entries(source)
    assert {row['code'] for row in diagnostics} == {'required', 'one-of'}
    assert any(row['field'] == 'journal' for row in diagnostics)
    assert source.entries[0]['title'] == 'Paper'

def test_editor_alternative():
    """书籍作者或编辑的替代组生效。@return None。"""
    from bibtexparser.validation import validate_entries
    source = Library([Entry('book', 'x', [Field('title', 'Book'), Field('year', '2026'), Field('publisher', 'P'), Field('editor', 'E')])])
    assert validate_entries(source) == ()

def test_custom_rules_and_empty():
    """可配置规则区分空字段和未知字段。@return None。"""
    from bibtexparser.validation import validate_entries
    source = Library([Entry('custom', 'x', [Field('needed', ''), Field('extra', 'v')])])
    diagnostics = validate_entries(source, rules={'custom': {'required': ['needed'], 'allowed': ['needed']}})
    assert [row['code'] for row in diagnostics] == ['required', 'unknown-field']
