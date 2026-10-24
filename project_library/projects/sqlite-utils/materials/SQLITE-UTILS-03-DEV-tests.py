"Public regression tests for SQLITE-UTILS-03-DEV; the complete business contract is in materials/SQLITE-UTILS-03-DEV-contract.md."
import io
from sqlite_utils.utils import rows_from_file,Format

def test_single_column_names_urls_unicode_and_header_only():
    "Verify single column names urls unicode and header only."
    for text,expected in [('name\nAlice\nBob\n',[{'name':'Alice'},{'name':'Bob'}]),('url\nhttps://example.test/a\nhttps://example.test/b\n',[{'url':'https://example.test/a'},{'url':'https://example.test/b'}]),('姓名\n雪\n茶\n',[{'姓名':'雪'},{'姓名':'茶'}]),('name\n',[])]:
        rows,format=rows_from_file(io.BytesIO(text.encode()))
        assert list(rows)==expected and format is Format.CSV

def test_common_multicolumn_delimiters_and_explicit_dialect_remain():
    "Verify common multicolumn delimiters and explicit dialect remain."
    for delimiter in (',','\t',';','|'):
        text=f'name{delimiter}quantity\na{delimiter}1\nb{delimiter}2\n'
        rows,format=rows_from_file(io.BytesIO(text.encode()))
        assert list(rows)==[{'name':'a','quantity':'1'},{'name':'b','quantity':'2'}]
    import csv
    class Custom(csv.excel):delimiter=':'
    rows,_=rows_from_file(io.BytesIO(b'name:quantity\na:1\n'),format=Format.CSV,dialect=Custom)
    assert list(rows)==[{'name':'a','quantity':'1'}]

