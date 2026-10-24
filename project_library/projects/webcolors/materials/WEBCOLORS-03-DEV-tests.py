"""RGBA新增合同不能让既有RGB函数静默丢弃alpha。"""
import unittest
import webcolors
from webcolors.rgba import RGBA, hex_to_rgba, rgba_to_hex, rgba_to_rgb, rgb_to_rgba


def test_short_and_long_roundtrip_preserves_hidden_rgb():
    """所有分量及透明像素中的RGB无损保留。@return None。"""
    assert hex_to_rgba('#3698')==RGBA(51,102,153,136)
    assert rgba_to_hex(hex_to_rgba('#AbCd'))=='#aabbccdd'
    assert rgba_to_hex(hex_to_rgba('#ff000000'))=='#ff000000'
    assert rgba_to_rgb(rgb_to_rgba((1,2,3)))==(1,2,3)


def test_old_rgb_contract_and_invalid_rgba():
    """透明转换必须显式，坏分量与尾换行拒绝。@return None。"""
    for value in ('#3698','#33669980'):
        with unittest.TestCase().assertRaises(ValueError):webcolors.hex_to_rgb(value)
    for value in ('#abc','#abcdef','#abcd\n','abcd','#abcdefff!'):
        with unittest.TestCase().assertRaises(ValueError):hex_to_rgba(value)
    for values in ((True,0,0,255),(1,2,3,-1),(1.0,2,3,4)):
        with unittest.TestCase().assertRaises(ValueError):RGBA(*values)
    with unittest.TestCase().assertRaises(ValueError):rgba_to_rgb(RGBA(255,0,0,0))

