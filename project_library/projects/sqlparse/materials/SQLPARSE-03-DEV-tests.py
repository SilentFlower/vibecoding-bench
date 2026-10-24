"""中文、CRLF与分组位置都切回精确原字符，不伪称字节偏移。"""
import unittest
from sqlparse.sourcemap import SourceMap


def test_atomic_and_group_half_open_character_ranges():
    """每个叶子与Statement切片准确且偏移连续。@return None。"""
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
    """编码明确，编辑后映射失效不能继续报原坐标。@return None。"""
    mapping=SourceMap('SELECT 中文;'.encode('utf-16-le'),encoding='utf-16-le')
    assert mapping.original=='SELECT 中文;'
    assert SourceMap('').tokens()==()
    token=mapping.tokens()[0][0];token.value='updated'
    with unittest.TestCase().assertRaises(ValueError):mapping.span(token)

