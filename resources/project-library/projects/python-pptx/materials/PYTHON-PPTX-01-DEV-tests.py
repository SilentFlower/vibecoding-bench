"Public regression tests for PYTHON-PPTX-01-DEV; the complete business contract is in materials/PYTHON-PPTX-01-DEV-contract.md."
import unittest
from pptx.dml.color import RGBColor

def test_exact_hex_case_channels_and_serialization():
    "Verify exact hex case channels and serialization."
    assert RGBColor.from_string('abcdef')==RGBColor(171,205,239)
    assert str(RGBColor.from_string('00aF01'))=='00AF01'
    assert RGBColor.from_string('112233')==RGBColor(17,34,51)

def test_invalid_length_whitespace_unicode_prefix_type_are_clear_errors():
    "Verify invalid length whitespace unicode prefix type are clear errors."
    for value in ('11223','1122000','','#112233',' 112233','１12233','gg2233',None,b'112233',123456):
        with unittest.TestCase().assertRaises(ValueError):RGBColor.from_string(value)

