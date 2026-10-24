"Public regression tests for CSSSELECT-O04-DEV; the complete business contract is in materials/CSSSELECT-O04-DEV-contract.md."
from lxml import etree
import cssselect
import pytest

def test_static_plugin_real_match_and_isolation():
    "Verify static plugin real match and isolation."
    from cssselect.extensions import PluginTranslator
    p=PluginTranslator();p.register_pseudo('reviewed',lambda x:x.add_condition('@reviewed="yes"'))
    root=etree.fromstring('<root><p id="a" reviewed="yes"/><p id="b"/></root>')
    assert [e.get('id') for e in root.xpath(p.css_to_xpath('p:reviewed'))]==['a']
    with pytest.raises(cssselect.ExpressionError):PluginTranslator().css_to_xpath(':reviewed')
    assert p.css_to_xpath('p:first-child')==cssselect.GenericTranslator().css_to_xpath('p:first-child')

def test_function_tokens_and_arity():
    "Verify function tokens and arity."
    from cssselect.extensions import PluginTranslator
    p=PluginTranslator();p.register_pseudo('marked',lambda x,f:x.add_condition('@mark='+p.xpath_literal(f.arguments[0].value)),functional=True,min_args=1,max_args=1,version='2')
    assert '@mark' in p.css_to_xpath(':marked("a")')
    with pytest.raises(cssselect.ExpressionError):p.css_to_xpath(':marked()')
    with pytest.raises(cssselect.ExpressionError):p.css_to_xpath(':marked')
    assert p.extension_fingerprint()==(('marked',True,1,1,'2'),)

def test_conflicts_bad_results_and_html_configuration():
    "Verify conflicts bad results and html configuration."
    from cssselect.extensions import HTMLPluginTranslator
    p=HTMLPluginTranslator();p.register_pseudo('bad',lambda x:'not XPath')
    with pytest.raises(ValueError):p.register_pseudo('checked',lambda x:x)
    with pytest.raises(ValueError):p.register_pseudo('bad',lambda x:x)
    with pytest.raises(cssselect.ExpressionError):p.css_to_xpath(':bad')
    assert p.css_to_xpath('DIV').endswith('div')
