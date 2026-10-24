"""编译后可在不同真实树求值，不暴露可变解析树。"""
from lxml import etree
import cssselect
import pytest

def test_group_specificity_and_two_trees():
    """分支specificity保持各自值，XPath不绑定树。@return None。"""
    from cssselect.compiled import compile_selector
    result=compile_selector('p.item, #chosen')
    assert result.specificity==((0,1,1),(1,0,0)) and result.canonical==('p.item','#chosen')
    for text in ['<root><p class="item"/></root>','<root><x id="chosen"/></root>']:
        assert len(etree.fromstring(text).xpath(result.xpath))==1
    assert result.xpath==cssselect.GenericTranslator().css_to_xpath('p.item, #chosen')

def test_modes_and_prefix_do_not_mix():
    """HTML大小写模式和作用域都是结果事实。@return None。"""
    from cssselect.compiled import compile_selector
    html=compile_selector('DIV',mode='html',prefix='self::')
    xml=compile_selector('DIV',prefix='self::')
    assert html.xpath=='self::div' and xml.xpath=='self::DIV' and html.mode=='html'
    assert compile_selector('DIV',mode='html',xhtml=True).xpath.endswith('DIV')

def test_immutable_and_native_errors():
    """结果不可改写，伪元素和语法继续拒绝。@return None。"""
    from dataclasses import FrozenInstanceError
    from cssselect.compiled import compile_selector
    with pytest.raises(FrozenInstanceError):compile_selector('p').xpath='changed'
    with pytest.raises(cssselect.ExpressionError):compile_selector('p::before')
    with pytest.raises(cssselect.SelectorSyntaxError):compile_selector('[')
