"Public regression tests for WEBCOLORS-01-DEV; the complete business contract is in materials/WEBCOLORS-01-DEV-contract.md."
import unittest
import webcolors


def test_css4_public_registry_and_legacy_keyword():
    "Verify css4 public registry and legacy keyword."
    assert webcolors.CSS4=='css4'
    assert webcolors.name_to_hex('RebeccaPurple')=='#663399'
    assert webcolors.hex_to_name('#639')=='rebeccapurple'
    assert webcolors.name_to_rgb('rebeccapurple',spec=webcolors.CSS4)==(102,51,153)
    assert 'rebeccapurple' in webcolors.names()
    assert webcolors.html5_parse_legacy_color('REBECCAPURPLE')==(102,51,153)


def test_older_specs_and_canonical_aliases_remain_isolated():
    "Verify older specs and canonical aliases remain isolated."
    for spec in (webcolors.HTML4,webcolors.CSS2,webcolors.CSS21,webcolors.CSS3):
        assert 'rebeccapurple' not in webcolors.names(spec)
        with unittest.TestCase().assertRaises(ValueError):webcolors.name_to_hex('rebeccapurple',spec)
    assert webcolors.hex_to_name('#808080')=='gray'
    result=webcolors.names();result.clear()
    assert len(webcolors.names(webcolors.CSS4))==148

