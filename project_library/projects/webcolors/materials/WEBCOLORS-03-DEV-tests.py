"Public regression tests for WEBCOLORS-03-DEV; the complete business contract is in materials/WEBCOLORS-03-DEV-contract.md."
import unittest
import webcolors
from webcolors.rgba import RGBA, hex_to_rgba, rgba_to_hex, rgba_to_rgb, rgb_to_rgba


def test_short_and_long_roundtrip_preserves_hidden_rgb():
    "Verify short and long roundtrip preserves hidden rgb."
    assert hex_to_rgba('#3698')==RGBA(51,102,153,136)
    assert rgba_to_hex(hex_to_rgba('#AbCd'))=='#aabbccdd'
    assert rgba_to_hex(hex_to_rgba('#ff000000'))=='#ff000000'
    assert rgba_to_rgb(rgb_to_rgba((1,2,3)))==(1,2,3)


def test_old_rgb_contract_and_invalid_rgba():
    "Verify old rgb contract and invalid rgba."
    for value in ('#3698','#33669980'):
        with unittest.TestCase().assertRaises(ValueError):webcolors.hex_to_rgb(value)
    for value in ('#abc','#abcdef','#abcd\n','abcd','#abcdefff!'):
        with unittest.TestCase().assertRaises(ValueError):hex_to_rgba(value)
    for values in ((True,0,0,255),(1,2,3,-1),(1.0,2,3,4)):
        with unittest.TestCase().assertRaises(ValueError):RGBA(*values)
    with unittest.TestCase().assertRaises(ValueError):rgba_to_rgb(RGBA(255,0,0,0))

