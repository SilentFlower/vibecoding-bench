"Public regression tests for CSSSELECT-O05-DEV; the complete business contract is in materials/CSSSELECT-O05-DEV-contract.md."
from lxml import etree
import cssselect
import pytest

def test_eligible_controls_and_complement():
    "Verify eligible controls and complement."
    from cssselect.formstates import FormStateTranslator
    root=etree.fromstring('<root><input id="a" required=""/><input id="b"/><select id="c" required=""/><textarea id="d"/><input id="e" type="checkbox" required=""/></root>')
    p=FormStateTranslator()
    assert [x.get('id') for x in root.xpath(p.css_to_xpath(':required'))]==['a','c','e']
    assert [x.get('id') for x in root.xpath(p.css_to_xpath(':optional'))]==['b','d']

def test_excluded_types_unknown_type_and_disabled():
    "Verify excluded types unknown type and disabled."
    from cssselect.formstates import FormStateTranslator
    root=etree.fromstring('<root><input id="x" type="HIDDEN" required=""/><div required=""/><input id="a" type="unknown" required=""/><input id="b" disabled="" required=""/></root>')
    assert [x.get('id') for x in root.xpath(FormStateTranslator().css_to_xpath(':required'))]==['a','b']
    with pytest.raises(cssselect.ExpressionError):cssselect.GenericTranslator().css_to_xpath(':required')

def test_xhtml_namespace_and_foreign_names():
    "Verify xhtml namespace and foreign names."
    from cssselect.formstates import FormStateTranslator
    root=etree.fromstring('<root xmlns:h="http://www.w3.org/1999/xhtml" xmlns:o="urn:other"><h:input id="yes" required=""/><o:input id="no" required=""/></root>')
    assert [x.get('id') for x in root.xpath(FormStateTranslator(xhtml=True).css_to_xpath(':required'))]==['yes']
