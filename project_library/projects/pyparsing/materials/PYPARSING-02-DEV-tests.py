"""字节导入实际结果与失败原字节位置一致。"""
import codecs
import unittest
import pyparsing as pp
from pyparsing.byte_input import parse_bytes,ByteParseError

def test_utf8_bom_unicode_and_tabs_keep_original_coordinates():
    """tab不扩展，BOM不算业务字符但字节坐标包含它。@return None。"""
    grammar=pp.Literal('茶')+pp.Literal('x');before=grammar.keepTabs
    value=parse_bytes(grammar,codecs.BOM_UTF8+'茶\tx'.encode(),encoding='utf-8-sig',parse_all=True)
    assert value.results.as_list()==['茶','x'] and value.text=='茶\tx'
    assert value.byte_offsets==(3,6,7,8) and grammar.keepTabs==before

def test_parse_error_decode_error_eof_and_explicit_codec_policy():
    """失败区分解码与语法，EOF精确映射到len(bytes)。@return None。"""
    with unittest.TestCase().assertRaises(ByteParseError) as caught:
        parse_bytes(pp.Literal('茶')+'x','茶?'.encode(),encoding='utf8',parse_all=True)
    assert caught.exception.byte_offset==3 and caught.exception.error.loc==1
    with unittest.TestCase().assertRaises(UnicodeDecodeError):parse_bytes(pp.Empty(),b'\xff',encoding='utf8')
    with unittest.TestCase().assertRaises(ValueError):parse_bytes(pp.Empty(),b'abc',encoding='utf-16')
    with unittest.TestCase().assertRaises(ByteParseError) as eof:parse_bytes(pp.Literal('ab'),b'a',encoding='ascii',parse_all=True)
    assert eof.exception.byte_offset in (0,1)

