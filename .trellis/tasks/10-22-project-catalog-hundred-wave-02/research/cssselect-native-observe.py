"""在真实lxml树上求值候选CSS转换结果，保留命名空间和模式差异。"""
import json
import os
from pathlib import Path
import sys

import cssselect
from cssselect import GenericTranslator, HTMLTranslator, SelectorSyntaxError
from lxml import etree, html


def ids(document, expression: str, **options) -> list:
    """求值实际XPath并取业务ID。@param document 文档。@param expression XPath。@param options 原生选项。@return ID列表。"""
    return [element.get('id') for element in document.xpath(expression, **options)]


def main() -> None:
    """验证一个固定业务，不调用浏览器或外部页面。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(cssselect.__file__).resolve() == root / 'library/cssselect/__init__.py'}
    task = sys.argv[1]
    translator = GenericTranslator()
    if task == 'CS-U01':
        document = etree.XML('<main id="root" class="active"><p id="a" class="active wide"/><p id="b" class="inactive"/></main>')
        result['default_scope_includes_context_and_class_matching_uses_whitespace_tokens'] = (
            ids(document, translator.css_to_xpath('.active')) == ['root', 'a']
            and ids(document, translator.css_to_xpath('p.active')) == ['a']
            and ids(document, translator.css_to_xpath('p:not(.active)')) == ['b'])
    elif task == 'CS-U02':
        document = etree.XML('<root xmlns="urn:local" xmlns:o="urn:other"><item id="a"/><o:item id="b"/></root>')
        expression = translator.css_to_xpath('d|item')
        missing = False
        try:
            document.xpath(expression)
        except etree.XPathEvalError:
            missing = True
        result['xpath_namespace_mapping_matches_uri_and_bare_names_do_not_match_default_namespace'] = (
            ids(document, expression, namespaces={'d': 'urn:local'}) == ['a']
            and ids(document, translator.css_to_xpath('o|item'), namespaces={'o': 'urn:other'}) == ['b']
            and ids(document, translator.css_to_xpath('item')) == [] and missing)
    elif task == 'CS-C01':
        document = html.fromstring('<DIV id="a" CLASS="Notice"></DIV>')
        result['html_mode_normalizes_names_but_preserves_class_value_case'] = (
            ids(document, HTMLTranslator().css_to_xpath('DIV.Notice')) == ['a']
            and ids(document, translator.css_to_xpath('DIV.Notice')) == []
            and ids(document, HTMLTranslator().css_to_xpath('div.notice')) == []
            and ids(etree.XML('<DIV id="b" CLASS="Notice"/>'),
                HTMLTranslator(xhtml=True).css_to_xpath('DIV[CLASS="Notice"]')) == ['b'])
    elif task == 'CS-C02':
        document = html.fromstring('<form><input id="checked" type="checkbox" checked><input id="plain" type="checkbox"><input id="text" type="text" checked><select><option id="selected" selected>X</option></select></form>')
        result['html_checked_reads_supported_serialized_attributes_not_live_browser_state'] = (
            ids(document, HTMLTranslator().css_to_xpath(':checked')) == ['checked', 'selected']
            and ids(document, translator.css_to_xpath(':checked')) == [])
    elif task == 'CS-P01':
        document = etree.XML('<root><main id="a"><p class="active"/></main><main id="b"><p/></main></root>')
        rejected = False
        try:
            translator.css_to_xpath('main:has(:scope)')
        except SelectorSyntaxError:
            rejected = True
        result['supported_has_queries_execute_and_unsupported_scope_is_an_error_not_no_matches'] = (
            ids(document, translator.css_to_xpath('main:has(> p.active)')) == ['a'] and rejected)
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
