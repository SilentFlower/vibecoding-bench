"""以实际Token和输出核章节提取、树遍历、HTML政策和Markdown往返。"""
import json
import os
from pathlib import Path
import sys

import mistletoe
from mistletoe import Document, HtmlRenderer
from mistletoe.markdown_renderer import MarkdownRenderer
from mistletoe.span_token import Strong
from mistletoe.utils import traverse


def html(source: str, **options) -> str:
    """在对应renderer上下文内解析原文。@param source 文本。@param options 原生选项。@return HTML。"""
    with HtmlRenderer(**options) as renderer:
        return renderer.render(Document(source))


def main() -> None:
    """返回独立事实，不执行HTML或修改候选。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(mistletoe.__file__).resolve() == root / 'library/mistletoe/__init__.py'}
    task = sys.argv[1]
    if task == 'MT-U01':
        with HtmlRenderer() as renderer:
            document = Document('# Alpha\n\n## Beta\n')
            headings = document.children
            visible = renderer.render(document)
            result['heading_child_text_is_per_node_while_content_is_shared_parse_state'] = (
                [node.content for node in headings] == ['Beta', 'Beta']
                and [node.children[0].content for node in headings] == ['Alpha', 'Beta']
                and '<h1>Alpha</h1>' in visible and '<h2>Beta</h2>' in visible)
    elif task == 'MT-U02':
        with HtmlRenderer():
            document = Document('# Stock\n\nText **bold**\n')
            records = list(traverse(document, include_source=True))
            strong = list(traverse(document, klass=Strong))
            result['traverse_is_breadth_first_and_reports_existing_parent_depth'] = (
                records[0].node is document and records[0].parent is None and records[0].depth == 0
                and [type(row.node).__name__ for row in records[1:3]] == ['Heading', 'Paragraph']
                and all(row.depth == 1 for row in records[1:3]) and len(strong) == 1 and strong[0].depth == 2
                and strong[0].parent is strong[0].node.parent
                and list(traverse(document, klass=Strong, depth=1)) == [])
    elif task == 'MT-C01':
        source = '<b>A</b>\n\n[x](javascript:alert(1))\n'
        default, escaped = html(source), html(source, process_html_tokens=False)
        result['raw_html_toggle_does_not_supply_a_link_scheme_policy'] = (
            '<b>A</b>' in default and '&lt;b&gt;A&lt;/b&gt;' in escaped
            and 'href="javascript:alert(1)"' in default and 'href="javascript:alert(1)"' in escaped)
    elif task == 'MT-U03':
        source = '&#35; heading\n'
        before = html(source)
        with MarkdownRenderer() as renderer:
            rewritten = renderer.render(Document(source))
        after = html(rewritten)
        escaped = '\\# heading\n'
        with MarkdownRenderer() as renderer:
            control = renderer.render(Document(escaped))
        result['markdown_rewrite_can_change_escaped_literal_semantics'] = (
            '<p># heading</p>' in before and '<h1>heading</h1>' in after and before != after
            and html(escaped) == html(control))
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
