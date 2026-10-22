"""核浏览器式HTML恢复、上下文、命名空间和输出安全边界。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import html5lib


def main() -> None:
    """检查本次候选生成的实际树和序列化结果。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(html5lib.__file__).resolve() == root / 'library/html5lib/__init__.py'}
    task = argv[1]
    if task == 'H5-U01':
        tree = html5lib.parse('<table>outside<tr><td>A</td></tr></table>')
        result['html_table_recovery_moves_text_and_inserts_tbody'] = html5lib.serialize(tree, omit_optional_tags=False) == (
            '<html><head></head><body>outside<table><tbody><tr><td>A</td></tr></tbody></table></body></html>')
    elif task == 'H5-U02':
        fragment = '<tr><td>A</td></tr>'
        result['fragment_tree_depends_on_the_declared_container_context'] = [
            html5lib.serialize(html5lib.parseFragment(fragment, container=context), omit_optional_tags=False)
            for context in ('div', 'table', 'tbody')
        ] == ['A', '<tbody><tr><td>A</td></tr></tbody>', '<tr><td>A</td></tr>']
    elif task == 'H5-C01':
        tree = html5lib.parseFragment('<script>alert(1)</script><p onclick="go()">A</p>')
        rendered = html5lib.serialize(tree, omit_optional_tags=False)
        result['default_html_parsing_and_serialization_preserve_active_content'] = (
            '<script>alert(1)</script>' in rendered and 'onclick=go()' in rendered)
    elif task == 'H5-C02':
        tree = html5lib.parse('<p>Café&nbsp;€</p>')
        paragraph = tree.find('.//h:p', {'h': 'http://www.w3.org/1999/xhtml'})
        plain = html5lib.parse('<p>Café&nbsp;€</p>', namespaceHTMLElements=False)
        result['default_html_namespaces_affect_queries_and_entities_decode_to_text'] = (
            tree.find('.//p') is None and paragraph is not None and paragraph.text == 'Café\u00a0€'
            and plain.find('.//p').text == paragraph.text)
    elif task == 'H5-P01':
        source = '<p class=\'x\'>A&nbsp;B</p>'
        options = {'omit_optional_tags': False, 'quote_attr_values': 'always'}
        first = html5lib.serialize(html5lib.parse(source), **options)
        second = html5lib.serialize(html5lib.parse(first), **options)
        result['normalized_serialization_is_stable_for_the_control_and_not_source_preservation'] = (
            first == second and first != source and '<p class="x">A\u00a0B</p>' in first)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
