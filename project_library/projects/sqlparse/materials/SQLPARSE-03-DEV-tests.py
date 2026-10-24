"Public regression tests for SQLPARSE-03-DEV; the complete business contract is in materials/SQLPARSE-03-DEV-contract.md."
import unittest
from sqlparse.sourcemap import SourceMap


def test_atomic_and_group_half_open_character_ranges():
    "Verify atomic and group half open character ranges."
    text=' \r\nSELECT 中文, 1;\r\nSELECT e\u0301 FROM t;  '
    mapping=SourceMap(text)
    entries=mapping.tokens()
    assert ''.join(token.value for token,span in entries)==text
    assert entries[0][1].start==0 and entries[-1][1].end==len(text)
    for token,span in entries:
        assert text[span.start:span.end]==token.value
        prefix=text[:span.start]
        assert span.line==prefix.count('\n')+1
    for statement in mapping.statements:
        span=mapping.span(statement);assert text[span.start:span.end]==str(statement)


def test_bytes_empty_and_stale_tokens_reject():
    "Verify bytes empty and stale tokens reject."
    mapping=SourceMap('SELECT 中文;'.encode('utf-16-le'),encoding='utf-16-le')
    assert mapping.original=='SELECT 中文;'
    assert SourceMap('').tokens()==()
    token=mapping.tokens()[0][0];token.value='updated'
    with unittest.TestCase().assertRaises(ValueError):mapping.span(token)

