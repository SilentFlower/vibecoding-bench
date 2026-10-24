"""CSS函数真实解析到RGBA而非凭分隔符猜通道。"""
import unittest
from webcolors.rgba import RGBA
from webcolors.css_rgb import parse_css_rgb,serialize_css_rgb


def test_legacy_modern_and_percent_equivalence():
    """两种语法的数值与百分比得到同一字节。@return None。"""
    expected=RGBA(255,0,128,128)
    assert parse_css_rgb('rgba(255,0,128,0.5)')==expected
    assert parse_css_rgb('rgb(100% 0% 50% / 50%)')==expected
    assert parse_css_rgb('RGB(300 -2 1e2)')==RGBA(255,0,100,255)
    assert parse_css_rgb(serialize_css_rgb(expected))==expected


def test_malformed_or_unsupported_syntax_is_not_partially_consumed():
    """混合语法、非有限及未支持表达式明确拒绝。@return None。"""
    for raw in ('rgb(1,2,3 / .5)','rgb(1,2%,3)','rgb(1 2)','rgb(1 2 3 / 0.5 / 1)','rgb(nan 2 3)','rgb(1e999 2 3)','rgb(calc(1) 2 3)','rgb(1 2 none)','rgb(1 2 3)tail'):
        with unittest.TestCase().assertRaises(ValueError):parse_css_rgb(raw)

