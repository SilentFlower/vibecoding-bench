"""表单状态资格来自真实控件与类型，不等同属性存在。"""
from lxml import etree
import cssselect
import pytest

def test_eligible_controls_and_complement():
    """所有有资格控件分为required和optional。@return None。"""
    from cssselect.formstates import FormStateTranslator
    root=etree.fromstring('<root><input id="a" required=""/><input id="b"/><select id="c" required=""/><textarea id="d"/><input id="e" type="checkbox" required=""/></root>')
    p=FormStateTranslator()
    assert [x.get('id') for x in root.xpath(p.css_to_xpath(':required'))]==['a','c','e']
    assert [x.get('id') for x in root.xpath(p.css_to_xpath(':optional'))]==['b','d']

def test_excluded_types_unknown_type_and_disabled():
    """排除无资格类型，未知类型按text，禁用仍保留声明。@return None。"""
    from cssselect.formstates import FormStateTranslator
    root=etree.fromstring('<root><input id="x" type="HIDDEN" required=""/><div required=""/><input id="a" type="unknown" required=""/><input id="b" disabled="" required=""/></root>')
    assert [x.get('id') for x in root.xpath(FormStateTranslator().css_to_xpath(':required'))]==['a','b']
    with pytest.raises(cssselect.ExpressionError):cssselect.GenericTranslator().css_to_xpath(':required')

def test_xhtml_namespace_and_foreign_names():
    """XHTML控件有资格，外部命名空间同名节点不误选。@return None。"""
    from cssselect.formstates import FormStateTranslator
    root=etree.fromstring('<root xmlns:h="http://www.w3.org/1999/xhtml" xmlns:o="urn:other"><h:input id="yes" required=""/><o:input id="no" required=""/></root>')
    assert [x.get('id') for x in root.xpath(FormStateTranslator(xhtml=True).css_to_xpath(':required'))]==['yes']
