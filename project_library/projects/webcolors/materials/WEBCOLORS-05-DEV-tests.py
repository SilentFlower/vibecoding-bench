"Public regression tests for WEBCOLORS-05-DEV; the complete business contract is in materials/WEBCOLORS-05-DEV-contract.md."
import math
import unittest
from webcolors.rgba import RGBA
from webcolors.accessibility import relative_luminance,contrast_ratio,meets_contrast,contrast_on


def test_luminance_ratio_and_unrounded_threshold():
    "Verify luminance ratio and unrounded threshold."
    black,white=(0,0,0),(255,255,255)
    assert relative_luminance(black)==0 and relative_luminance(white)==1
    assert contrast_ratio(black,white)==contrast_ratio(white,black)==21
    assert contrast_ratio(black,black)==1 and meets_contrast(black,white,7)
    value=contrast_ratio((118,118,118),white)
    assert meets_contrast((118,118,118),white,value)
    assert not meets_contrast((118,118,118),white,math.nextafter(value,math.inf))


def test_transparency_and_invalid_data_are_explicit():
    "Verify transparency and invalid data are explicit."
    assert contrast_on(RGBA(255,0,0,0),(1,2,3))==1
    assert contrast_on(RGBA(0,0,0,255),(255,255,255))==21
    with unittest.TestCase().assertRaises(ValueError):relative_luminance(RGBA(0,0,0,128))
    for bad in ((True,0,0),(256,0,0),(1,2),(0.5,0,0)):
        with unittest.TestCase().assertRaises(ValueError):relative_luminance(bad)

