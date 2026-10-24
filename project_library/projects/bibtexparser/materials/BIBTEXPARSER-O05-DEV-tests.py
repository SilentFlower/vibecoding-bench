"""标识符只做可证伪的本地语法和校验位检查。"""
from bibtexparser import Library
from bibtexparser.model import Entry, Field

def test_doi_and_isbn():
    """DOI URL与合法ISBN规范化且原值可追溯。@return None。"""
    from bibtexparser.identifiers import NormalizeIdentifiers
    source = Library([Entry('book', 'x', [Field('doi', ' HTTPS://doi.org/10.1234/ABC '), Field('isbn', '978-0-306-40615-7')])])
    result = NormalizeIdentifiers().transform(source)
    assert result.entries[0]['doi'] == '10.1234/abc'
    assert result.entries[0]['isbn'] == '9780306406157'
    assert source.entries[0]['isbn'] == '978-0-306-40615-7'

def test_invalid_preserved_and_strict():
    """无效校验位保留报告或显式失败。@return None。"""
    import pytest
    from bibtexparser.identifiers import NormalizeIdentifiers
    source = Library([Entry('book', 'x', [Field('isbn', '9780306406158')])])
    result = NormalizeIdentifiers().transform(source)
    assert result.entries[0]['isbn'] == '9780306406158'
    assert result.entries[0].parser_metadata['identifiers']['isbn']['status'] == 'invalid'
    with pytest.raises(ValueError): NormalizeIdentifiers(strict=True).transform(source)

def test_selected_fields_and_isbn10():
    """字段白名单及ISBN10大写X边界。@return None。"""
    from bibtexparser.identifiers import NormalizeIdentifiers
    source = Library([Entry('book', 'x', [Field('isbn', '0-8044-2957-x'), Field('doi', 'doi:10.1234/KEEP')])])
    result = NormalizeIdentifiers(fields=('isbn',)).transform(source)
    assert result.entries[0]['isbn'] == '080442957X' and result.entries[0]['doi'] == 'doi:10.1234/KEEP'
