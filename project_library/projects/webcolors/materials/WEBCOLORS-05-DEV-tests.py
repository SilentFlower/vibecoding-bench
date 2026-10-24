"""主题对比度使用真实sRGB公式和明确背景，不暗选白色。"""
import math
import unittest
from webcolors.rgba import RGBA
from webcolors.accessibility import relative_luminance,contrast_ratio,meets_contrast,contrast_on


def test_luminance_ratio_and_unrounded_threshold():
    """黑白21比1、对称及严格阈值比较。@return None。"""
    black,white=(0,0,0),(255,255,255)
    assert relative_luminance(black)==0 and relative_luminance(white)==1
    assert contrast_ratio(black,white)==contrast_ratio(white,black)==21
    assert contrast_ratio(black,black)==1 and meets_contrast(black,white,7)
    value=contrast_ratio((118,118,118),white)
    assert meets_contrast((118,118,118),white,value)
    assert not meets_contrast((118,118,118),white,math.nextafter(value,math.inf))


def test_transparency_and_invalid_data_are_explicit():
    """透明色只有指定背景后才能参与比值。@return None。"""
    assert contrast_on(RGBA(255,0,0,0),(1,2,3))==1
    assert contrast_on(RGBA(0,0,0,255),(255,255,255))==21
    with unittest.TestCase().assertRaises(ValueError):relative_luminance(RGBA(0,0,0,128))
    for bad in ((True,0,0),(256,0,0),(1,2),(0.5,0,0)):
        with unittest.TestCase().assertRaises(ValueError):relative_luminance(bad)

