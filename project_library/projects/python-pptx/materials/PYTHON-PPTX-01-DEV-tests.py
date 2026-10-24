"""RGB输入严格六位ASCII十六进制，不把CSS语法当现有合同。"""
import unittest
from pptx.dml.color import RGBColor

def test_exact_hex_case_channels_and_serialization():
    """合法大小写等值，输出固定六位大写。@return None。"""
    assert RGBColor.from_string('abcdef')==RGBColor(171,205,239)
    assert str(RGBColor.from_string('00aF01'))=='00AF01'
    assert RGBColor.from_string('112233')==RGBColor(17,34,51)

def test_invalid_length_whitespace_unicode_prefix_type_are_clear_errors():
    """五/七位不能静默成为其他颜色。@return None。"""
    for value in ('11223','1122000','','#112233',' 112233','１12233','gg2233',None,b'112233',123456):
        with unittest.TestCase().assertRaises(ValueError):RGBColor.from_string(value)

