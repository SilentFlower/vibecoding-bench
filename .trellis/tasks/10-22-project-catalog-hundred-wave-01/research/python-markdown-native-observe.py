"""观察候选Markdown的文档状态、惰性HTML、目录及明确扩展加载。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import markdown
from markdown import Markdown
from markdown.extensions.footnotes import FootnoteExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension, slugify_unicode


FIRST = 'Coffee[^a]\n\n[^a]: first-note'
SECOND = 'Tea[^a]'


def documents() -> dict:
    """核真实脚注状态，不把共享实例自动重置当已存在能力。@return 文档边界事实。"""
    shared = Markdown(extensions=[FootnoteExtension()])
    shared.convert(FIRST)
    reused = shared.convert(SECOND)
    shared.reset()
    reset = shared.convert(SECOND)
    fresh = Markdown(extensions=[FootnoteExtension()]).convert(SECOND)
    return {'shared_instance_preserves_footnote_state': 'first-note' in reused,
        'reset_separates_document_state': 'first-note' not in reset and '[^a]' in reset,
        'fresh_instance_matches_reset_document': fresh == reset}


def raw_html() -> dict:
    """只观察惰性HTML字面，不执行任何HTML脚本或外部工具。@return 输出策略事实。"""
    source = '<span data-origin="comment">coffee</span>'
    output = Markdown().convert(source)
    return {'inert_raw_html_is_preserved': source in output,
        'code_span_escapes_literal_markup': '&lt;span' in Markdown().convert('`' + source + '`')}


def outline() -> dict:
    """核实际目录层级和中文slug回调。@return 目录与锚点事实。"""
    renderer = Markdown(extensions=[TocExtension(toc_depth='1-2')])
    output = renderer.convert('# Cafe\n\n## Menu\n\n## Menu\n\n### Hidden')
    tokens = renderer.toc_tokens
    unicode_renderer = Markdown(extensions=[TocExtension(slugify=slugify_unicode)])
    unicode_output = unicode_renderer.convert('# 咖啡\n\n## 菜单\n\n## 菜单')
    chinese = unicode_renderer.toc_tokens
    return {'toc_tokens_keep_hierarchy_and_unique_ids': len(tokens) == 1 and tokens[0]['id'] == 'cafe'
            and [item['id'] for item in tokens[0]['children']] == ['menu', 'menu_1'],
        'toc_depth_does_not_remove_body_heading': '<h3 id="hidden">Hidden</h3>' in output
            and all(not item['children'] for item in tokens[0]['children']),
        'existing_unicode_slugify_keeps_chinese': chinese[0]['id'] == '咖啡'
            and [item['id'] for item in chinese[0]['children']] == ['菜单', '菜单_1']
            and 'id="咖啡"' in unicode_output}


def extensions() -> dict:
    """对照显式扩展和未安装分发元数据的源码模式。@return 扩展及序列化事实。"""
    text = '| Item | Qty |\n| --- | ---: |\n| Tea | 2 |'
    bare = Markdown().convert(text)
    table = Markdown(extensions=[TableExtension()]).convert(text)
    full = Markdown(extensions=['markdown.extensions.tables']).convert(text)
    alias_missing = False
    try:
        Markdown(extensions=['tables']).convert(text)
    except ModuleNotFoundError as error:
        alias_missing = error.name == 'tables'
    return {'table_requires_explicit_extension': '<table>' not in bare and '<table>' in table and 'Tea' in table,
        'html_xhtml_empty_element_formats': Markdown(output_format='html').convert('---') == '<hr>'
            and Markdown(output_format='xhtml').convert('---') == '<hr />',
        'source_only_full_module_and_instance_work': full == table and alias_missing}


def main() -> None:
    """输出当前任务的真实源码和行为观察。@return None。"""
    task = sys.argv[1]
    fields = {'PM-U01': ('shared_instance_preserves_footnote_state', 'reset_separates_document_state', 'fresh_instance_matches_reset_document'),
        'PM-C01': ('inert_raw_html_is_preserved', 'code_span_escapes_literal_markup'),
        'PM-P01': ('inert_raw_html_is_preserved', 'reset_separates_document_state'),
        'PM-U02': ('toc_tokens_keep_hierarchy_and_unique_ids', 'toc_depth_does_not_remove_body_heading'),
        'PM-C02': ('existing_unicode_slugify_keeps_chinese',),
        'PM-U03': ('table_requires_explicit_extension', 'html_xhtml_empty_element_formats'),
        'PM-C03': ('source_only_full_module_and_instance_work',)}
    if task == 'PM-U01':
        facts = documents()
    elif task == 'PM-C01':
        facts = raw_html()
    elif task == 'PM-P01':
        facts = {**raw_html(), **documents()}
    elif task in ('PM-U02', 'PM-C02'):
        facts = outline()
    else:
        facts = extensions()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(markdown.__file__).resolve() == root / 'library/markdown/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
