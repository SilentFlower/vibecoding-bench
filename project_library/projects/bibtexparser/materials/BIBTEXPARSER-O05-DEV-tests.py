"Public regression tests for BIBTEXPARSER-O05-DEV; the complete business contract is in materials/BIBTEXPARSER-O05-DEV-contract.md."
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_doi_and_isbn():
    "Verify doi and isbn."
    from bibtexparser.identifiers import NormalizeIdentifiers
    source = Library([Entry('book', 'x', [Field('doi', ' HTTPS://doi.org/10.1234/ABC '), Field('isbn', '978-0-306-40615-7')])])
    result = NormalizeIdentifiers().transform(source)
    assert result.entries[0]['doi'] == '10.1234/abc'
    assert result.entries[0]['isbn'] == '9780306406157'
    assert source.entries[0]['isbn'] == '978-0-306-40615-7'

def test_invalid_preserved_and_strict():
    "Verify invalid preserved and strict."
    import pytest
    from bibtexparser.identifiers import NormalizeIdentifiers
    source = Library([Entry('book', 'x', [Field('isbn', '9780306406158')])])
    result = NormalizeIdentifiers().transform(source)
    assert result.entries[0]['isbn'] == '9780306406158'
    assert result.entries[0].parser_metadata['identifiers']['isbn']['status'] == 'invalid'
    with pytest.raises(ValueError): NormalizeIdentifiers(strict=True).transform(source)

def test_selected_fields_and_isbn10():
    "Verify selected fields and isbn10."
    from bibtexparser.identifiers import NormalizeIdentifiers
    source = Library([Entry('book', 'x', [Field('isbn', '0-8044-2957-x'), Field('doi', 'doi:10.1234/KEEP')])])
    result = NormalizeIdentifiers(fields=('isbn',)).transform(source)
    assert result.entries[0]['isbn'] == '080442957X' and result.entries[0]['doi'] == 'doi:10.1234/KEEP'
