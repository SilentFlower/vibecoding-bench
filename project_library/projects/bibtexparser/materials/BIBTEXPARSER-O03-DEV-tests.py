"Public regression tests for BIBTEXPARSER-O03-DEV; the complete business contract is in materials/BIBTEXPARSER-O03-DEV-contract.md."
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_numeric_ranges():
    "Verify numeric ranges."
    from bibtexparser.pages import NormalizePages
    source = Library([Entry('article', 'x', [Field('pages', '12-19, 23–24'), Field('title', 'a-b')])])
    result = NormalizePages().transform(source)
    assert result.entries[0]['pages'] == '12--19, 23--24'
    assert result.entries[0]['title'] == 'a-b' and source.entries[0]['pages'] == '12-19, 23–24'

def test_unknown_and_descending_preserved():
    "Verify unknown and descending preserved."
    from bibtexparser.pages import NormalizePages
    for pages in ('e123', 'iv-v', '9-2', '', '12.5-13.5'):
        assert NormalizePages().transform(Library([Entry('article', 'x', [Field('pages', pages)])])).entries[0]['pages'] == pages

def test_idempotent_and_original():
    "Verify idempotent and original."
    from bibtexparser.pages import NormalizePages
    result = NormalizePages().transform(Library([Entry('article', 'x', [Field('pages', '1—3')])]))
    again = NormalizePages().transform(result)
    assert again.entries[0]['pages'] == '1--3'
    assert again.entries[0].parser_metadata['original_pages'] == '1—3'
