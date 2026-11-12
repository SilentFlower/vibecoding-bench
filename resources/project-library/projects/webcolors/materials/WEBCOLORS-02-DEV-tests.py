"Public regression tests for WEBCOLORS-02-DEV; the complete business contract is in materials/WEBCOLORS-02-DEV-contract.md."
import unittest
import webcolors


def test_non_ascii_whitespace_remains_input_data():
    "Verify non ascii whitespace remains input data."
    assert webcolors.html5_parse_legacy_color('\u00a0red\u00a0')==(0,237,0)
    assert webcolors.html5_parse_legacy_color('red')==(255,0,0)


def test_ascii_trim_and_strict_simple_are_separate():
    "Verify ascii trim and strict simple are separate."
    for char in (' ','\t','\n','\r','\f'):
        assert webcolors.html5_parse_legacy_color(char+'red'+char)==(255,0,0)
    with unittest.TestCase().assertRaises(ValueError):webcolors.html5_parse_legacy_color(' transparent ')
    with unittest.TestCase().assertRaises(ValueError):webcolors.html5_parse_simple_color(' #ff0000 ')
    assert webcolors.html5_parse_legacy_color(' \t\n')==(0,0,0)

