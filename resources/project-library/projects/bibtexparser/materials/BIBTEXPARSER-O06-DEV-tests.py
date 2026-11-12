"Public regression tests for BIBTEXPARSER-O06-DEV; the complete business contract is in materials/BIBTEXPARSER-O06-DEV-contract.md."
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_field_order_not_change():
    "Verify field order not change."
    from bibtexparser.diff import diff_libraries
    one = Library([Entry('ARTICLE', 'x', [Field('title', 'A'), Field('year', '2026')])])
    two = Library([Entry('article', 'x', [Field('year', '2026'), Field('title', 'A')])])
    assert diff_libraries(one, two)['entries'] == {'added': [], 'removed': [], 'changed': []}

def test_changes_and_added_removed():
    "Verify changes and added removed."
    from bibtexparser.diff import diff_libraries
    one = Library([Entry('article', 'x', [Field('title', 'A')]), Entry('book', 'old', [])])
    two = Library([Entry('article', 'x', [Field('title', 'B')]), Entry('book', 'new', [])])
    result = diff_libraries(one, two)['entries']
    assert result['added'] == ['new'] and result['removed'] == ['old']
    assert result['changed'][0]['key'] == 'x'

def test_ignored_and_nonentry_blocks():
    "Verify ignored and nonentry blocks."
    from bibtexparser.diff import diff_libraries
    from bibtexparser.model import String, ExplicitComment
    one = Library([Entry('article', 'x', [Field('year', '1')]), String('m', 'one'), ExplicitComment('a')])
    two = Library([Entry('article', 'x', [Field('year', '2')]), String('m', 'two'), ExplicitComment('b')])
    result = diff_libraries(one, two, ignore_fields=['year'])
    assert result['entries']['changed'] == [] and result['strings'] is not None and result['comments'] is not None
