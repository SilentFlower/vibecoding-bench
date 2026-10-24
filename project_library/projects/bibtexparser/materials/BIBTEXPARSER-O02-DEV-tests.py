"Public regression tests for BIBTEXPARSER-O02-DEV; the complete business contract is in materials/BIBTEXPARSER-O02-DEV-contract.md."
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_article_required_fields():
    "Verify article required fields."
    from bibtexparser.validation import validate_entries
    source = Library([Entry('article', 'x', [Field('title', 'Paper'), Field('year', '2026')])])
    diagnostics = validate_entries(source)
    assert {row['code'] for row in diagnostics} == {'required', 'one-of'}
    assert any(row['field'] == 'journal' for row in diagnostics)
    assert source.entries[0]['title'] == 'Paper'

def test_editor_alternative():
    "Verify editor alternative."
    from bibtexparser.validation import validate_entries
    source = Library([Entry('book', 'x', [Field('title', 'Book'), Field('year', '2026'), Field('publisher', 'P'), Field('editor', 'E')])])
    assert validate_entries(source) == ()

def test_custom_rules_and_empty():
    "Verify custom rules and empty."
    from bibtexparser.validation import validate_entries
    source = Library([Entry('custom', 'x', [Field('needed', ''), Field('extra', 'v')])])
    diagnostics = validate_entries(source, rules={'custom': {'required': ['needed'], 'allowed': ['needed']}})
    assert [row['code'] for row in diagnostics] == ['required', 'unknown-field']
