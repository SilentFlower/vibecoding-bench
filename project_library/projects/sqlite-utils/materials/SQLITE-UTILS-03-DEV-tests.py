"""自动导入单列姓名和URL，不把普通字母误当分隔符。"""
import io
from sqlite_utils.utils import rows_from_file,Format

def test_single_column_names_urls_unicode_and_header_only():
    """真实返回行字典，不以检测结果标签冒认导入。@return None。"""
    for text,expected in [('name\nAlice\nBob\n',[{'name':'Alice'},{'name':'Bob'}]),('url\nhttps://example.test/a\nhttps://example.test/b\n',[{'url':'https://example.test/a'},{'url':'https://example.test/b'}]),('姓名\n雪\n茶\n',[{'姓名':'雪'},{'姓名':'茶'}]),('name\n',[])]:
        rows,format=rows_from_file(io.BytesIO(text.encode()))
        assert list(rows)==expected and format is Format.CSV

def test_common_multicolumn_delimiters_and_explicit_dialect_remain():
    """常见逗号/Tab/分号/管道仍由真实CSV解析，显式dialect不改。@return None。"""
    for delimiter in (',','\t',';','|'):
        text=f'name{delimiter}quantity\na{delimiter}1\nb{delimiter}2\n'
        rows,format=rows_from_file(io.BytesIO(text.encode()))
        assert list(rows)==[{'name':'a','quantity':'1'},{'name':'b','quantity':'2'}]
    import csv
    class Custom(csv.excel):delimiter=':'
    rows,_=rows_from_file(io.BytesIO(b'name:quantity\na:1\n'),format=Format.CSV,dialect=Custom)
    assert list(rows)==[{'name':'a','quantity':'1'}]

