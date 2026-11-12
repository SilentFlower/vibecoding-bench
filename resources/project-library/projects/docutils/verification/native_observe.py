"""独立观察Docutils发布树、错误阈值、指令权限和稳定标识。"""
from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import docutils
from docutils import nodes
from docutils.core import publish_doctree, publish_parts, publish_string
from docutils.utils import SystemMessage


def settings(**overrides) -> dict:
    """隔离外部配置和诊断输出，不改变上游默认指令能力。@param overrides 本案例明确设置。@return 独立发布设置。"""
    return {'_disable_config': True, 'warning_stream': StringIO(), 'report_level': 2, 'halt_level': 6,
        'stylesheet_path': '', **overrides}


def publishing() -> dict:
    """核标题提升和输出类型，不混淆片段与整页。@return 发布事实。"""
    source = 'Title\n=====\n\nCoffee 咖啡.\n'
    promoted = publish_doctree(source, settings_overrides=settings())
    sections = publish_doctree(source, settings_overrides=settings(doctitle_xform=False))
    parts = publish_parts(source, writer='html5', settings_overrides=settings())
    encoded = publish_string(source, writer='html5', settings_overrides=settings(output_encoding='utf-8'))
    text = publish_string(source, writer='html5', settings_overrides=settings(output_encoding='unicode'))
    return {'first_section_can_be_promoted_to_document_title': not list(promoted.findall(nodes.section))
            and len(list(promoted.findall(nodes.title))) == 1 and len(list(sections.findall(nodes.section))) == 1,
        'parts_and_string_have_explicit_output_ownership': isinstance(parts['fragment'], str)
            and '咖啡' in parts['fragment'] and '<html' not in parts['fragment']
            and isinstance(encoded, bytes) and '咖啡' in encoded.decode('utf-8')
            and isinstance(text, str) and '咖啡' in text and '<html' in text}


def reference_errors() -> dict:
    """核报告阈值不是失败阈值。@return 引用诊断事实。"""
    source = 'See missing_.\n'
    doc = publish_doctree(source, source_path='guide.rst', settings_overrides=settings())
    # null writer不把游离转换消息插入正文；诊断仍由原生document保存，不能只遍历正文。
    messages = [*doc.findall(nodes.system_message), *doc.parse_messages, *doc.transform_messages]
    muted = publish_doctree(source, source_path='guide.rst', settings_overrides=settings(report_level=5))
    stopped = False
    try:
        publish_doctree(source, source_path='guide.rst', settings_overrides=settings(halt_level=3))
    except SystemMessage:
        stopped = True
    return {'unresolved_reference_is_reported_without_default_programmatic_failure': any(
            message['level'] == 3 and 'missing' in message.astext() for message in messages)
            and bool(list(doc.findall(nodes.problematic))),
        'halt_level_controls_failure_even_when_report_level_differs': stopped
            and bool(list(muted.findall(nodes.problematic)))}


def directive_permissions() -> dict:
    """只用本轮合成文件核include与raw权限，不读取外部数据。@return 指令事实。"""
    raw = '.. raw:: html\n\n   <b>trusted-marker</b>\n'
    trusted = publish_doctree(raw, settings_overrides=settings())
    blocked = publish_doctree(raw, settings_overrides=settings(raw_enabled=False))
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'fragment.rst').write_text('synthetic-include-marker\n')
        allowed = publish_doctree('.. include:: fragment.rst\n', source_path=str(root / 'main.rst'),
            settings_overrides=settings())
        denied = publish_doctree('.. include:: fragment.rst\n', source_path=str(root / 'main.rst'),
            settings_overrides=settings(file_insertion_enabled=False))
    link = publish_doctree('`guide <https://example.test/guide>`_\n',
        settings_overrides=settings(raw_enabled=False, file_insertion_enabled=False))
    return {'raw_and_include_are_separately_controlled': len(list(trusted.findall(nodes.raw))) == 1
            and not list(blocked.findall(nodes.raw)) and 'synthetic-include-marker' in allowed.astext()
            and 'synthetic-include-marker' not in denied.astext()
            and any('disabled' in message.astext() for message in denied.findall(nodes.system_message)),
        'directive_settings_do_not_remove_normal_external_links': any(
            ref.get('refuri') == 'https://example.test/guide' for ref in link.findall(nodes.reference))}


def stable_targets() -> dict:
    """核显式锚点在标题改名后保留，自动锚点依赖标题。@return 标识事实。"""
    def identifiers(title: str) -> set:
        """取实际树中全部ID。@param title 文档标题。@return 当前ID集合。"""
        doc = publish_doctree('.. _payments-api:\n\n' + title + '\n' + '=' * len(title) + '\n\nText.\n',
            settings_overrides=settings())
        return {identifier for node in doc.findall(nodes.Element) for identifier in node['ids']}

    first, second = identifiers('Payment methods'), identifiers('Payment endpoints')
    return {'explicit_targets_survive_title_rename': 'payments-api' in first & second
        and 'payment-methods' in first and 'payment-endpoints' in second
        and 'payment-methods' not in second}


def csv_table() -> dict:
    """核结构化CSV表格保留逗号单元格及Unicode。@return 表格事实。"""
    source = '.. csv-table:: Stock\n   :header: "item", "qty"\n\n   "tea, green", 2\n   "咖啡", 3\n'
    doc = publish_doctree(source, settings_overrides=settings())
    return {'csv_table_keeps_quoted_cells_and_unicode': len(list(doc.findall(nodes.table))) == 1
        and len(list(doc.findall(nodes.row))) == 3
        and [entry.astext() for entry in doc.findall(nodes.entry)] == ['item', 'qty', 'tea, green', '2', '咖啡', '3']}


def main() -> None:
    """核嵌套候选源码并输出任务独立事实。@return None。"""
    entries = {'DU-U01': (publishing, ['first_section_can_be_promoted_to_document_title']),
        'DU-C01': (publishing, ['parts_and_string_have_explicit_output_ownership']),
        'DU-C02': (reference_errors, ['unresolved_reference_is_reported_without_default_programmatic_failure', 'halt_level_controls_failure_even_when_report_level_differs']),
        'DU-C03': (directive_permissions, ['raw_and_include_are_separately_controlled']),
        'DU-P01': (directive_permissions, ['raw_and_include_are_separately_controlled', 'directive_settings_do_not_remove_normal_external_links']),
        'DU-U02': (stable_targets, ['explicit_targets_survive_title_rename']),
        'DU-U03': (csv_table, ['csv_table_keeps_quoted_cells_and_unicode'])}
    observe, fields = entries[sys.argv[1]]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(docutils.__file__).resolve() == root / 'library/docutils/docutils/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
