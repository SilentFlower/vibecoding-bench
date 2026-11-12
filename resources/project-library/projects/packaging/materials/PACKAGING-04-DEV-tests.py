"Public regression tests for PACKAGING-04-DEV; the complete business contract is in materials/PACKAGING-04-DEV-contract.md."
import base64
import hashlib
import unittest
from packaging.record import RecordEntry,parse_record,format_record

def test_record_roundtrip_csv_and_hashless_self_entry():
    "Verify record roundtrip csv and hashless self entry."
    digest=base64.urlsafe_b64encode(hashlib.sha256(b'payload').digest()).rstrip(b'=').decode()
    entries=(RecordEntry('pkg/data,中文.txt','sha256='+digest,7),RecordEntry('pkg.dist-info/RECORD'))
    text=format_record(entries)
    assert text.startswith('"pkg/data,中文.txt",sha256=') and parse_record(text)==entries
    assert parse_record('a,,0\n')[0].size==0

def test_invalid_columns_duplicates_sizes_and_hashes():
    "Verify invalid columns duplicates sizes and hashes."
    for text in ('a,b\n','a,,\na,,\n','a,,-1\n','a,,01\n','a,sha256=bad,1\n'):
        with unittest.TestCase().assertRaises(ValueError):parse_record(text)
    with unittest.TestCase().assertRaises(ValueError):RecordEntry('a',size=True)

