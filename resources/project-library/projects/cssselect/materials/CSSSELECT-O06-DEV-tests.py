"Public regression tests for CSSSELECT-O06-DEV; the complete business contract is in materials/CSSSELECT-O06-DEV-contract.md."
from lxml import etree
import cssselect
import pytest

def test_contenteditable_inherit_false_override_and_invalid():
    "Verify contenteditable inherit false override and invalid."
    from cssselect.editable import EditableStateTranslator
    root=etree.fromstring('<r><div id="a" contenteditable="true"><p id="b"/><div id="c" contenteditable="false"><b id="d"/></div><i id="e" contenteditable="invalid"/></div></r>')
    p=EditableStateTranslator();assert [x.get('id') for x in root.xpath(p.css_to_xpath(':read-write'))]==['a','b','e']
    writable=set(root.xpath(p.css_to_xpath(':read-write')));readonly=set(root.xpath(p.css_to_xpath(':read-only')))
    assert not writable&readonly and writable|readonly==set(root.iter())

def test_form_text_readonly_disabled_and_nontext():
    "Verify form text readonly disabled and nontext."
    from cssselect.editable import EditableStateTranslator
    root=etree.fromstring('<r contenteditable="true"><input id="a"/><input id="b" readonly=""/><input id="c" disabled=""/><input id="d" type="checkbox"/><textarea id="e"/><textarea id="f" readonly=""/></r>')
    ids=[x.get('id') for x in root.xpath(EditableStateTranslator().css_to_xpath(':read-write'))]
    assert ids==[None,'a','e']

def test_plaintext_case_xhtml_and_generic_unchanged():
    "Verify plaintext case xhtml and generic unchanged."
    from cssselect.editable import EditableStateTranslator
    root=etree.fromstring('<h:div xmlns:h="http://www.w3.org/1999/xhtml" contenteditable="PLAINTEXT-ONLY"><h:p id="yes"/></h:div>')
    assert len(root.xpath(EditableStateTranslator(xhtml=True).css_to_xpath(':read-write')))==2
    with pytest.raises(cssselect.ExpressionError):cssselect.GenericTranslator().css_to_xpath(':read-write')
