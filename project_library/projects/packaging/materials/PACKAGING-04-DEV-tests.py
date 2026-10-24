"""逗号、Unicode、空hash与精确size的CSV往返。"""
import base64
import hashlib
import unittest
from packaging.record import RecordEntry,parse_record,format_record

def test_record_roundtrip_csv_and_hashless_self_entry():
    """内容地址只校验字段，解析阶段不读文件。@return None。"""
    digest=base64.urlsafe_b64encode(hashlib.sha256(b'payload').digest()).rstrip(b'=').decode()
    entries=(RecordEntry('pkg/data,中文.txt','sha256='+digest,7),RecordEntry('pkg.dist-info/RECORD'))
    text=format_record(entries)
    assert text.startswith('"pkg/data,中文.txt",sha256=') and parse_record(text)==entries
    assert parse_record('a,,0\n')[0].size==0

def test_invalid_columns_duplicates_sizes_and_hashes():
    """不默默接受重复路径、负值或伪摘要。@return None。"""
    for text in ('a,b\n','a,,\na,,\n','a,,-1\n','a,,01\n','a,sha256=bad,1\n'):
        with unittest.TestCase().assertRaises(ValueError):parse_record(text)
    with unittest.TestCase().assertRaises(ValueError):RecordEntry('a',size=True)

