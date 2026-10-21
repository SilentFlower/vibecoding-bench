"""独立观察Rich字面渲染、样式、宽度与导出缓冲生命周期。"""
from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
import sys

import rich
from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape


def console(**overrides) -> tuple[Console, StringIO]:
    """构造与真实TTY、用户环境无关的合成输出目的地。@param overrides 本例参数。@return 控制台与输出流。"""
    stream = StringIO()
    return Console(**{'file': stream, 'width': 80, 'force_terminal': False, 'emoji': False,
        'highlight': False, '_environ': {}, **overrides}), stream


def literal_fields() -> dict:
    """核客户文本的标签解释与已有字面输出接口。@return 字面事实。"""
    value = '[red]urgent[/red]'
    interpreted, first = console()
    interpreted.print(value)
    literal, second = console()
    literal.print(value, markup=False)
    mixed, third = console()
    mixed.print('[bold]Item:[/bold] ' + escape(value))
    return {'literal_text_requires_explicit_markup_ownership': first.getvalue() == 'urgent\n'
        and second.getvalue() == value + '\n' and third.getvalue() == 'Item: ' + value + '\n'}


def terminal_styles() -> dict:
    """核no_color和彻底禁用ANSI的区别。@return 终端事实。"""
    redirected, first = console()
    redirected.print('ready', style='bold red')
    terminal, second = console(force_terminal=True, color_system='standard', no_color=True)
    terminal.print('ready', style='bold red')
    plain, third = console(force_terminal=True, color_system=None)
    plain.print('ready', style='bold red')
    return {'no_color_can_keep_non_color_terminal_styles': first.getvalue() == third.getvalue() == 'ready\n'
        and '\x1b[' in second.getvalue() and '\x1b[1m' in second.getvalue()
        and ';31' not in second.getvalue()}


def narrow_reports() -> dict:
    """核显示单元宽度和已裁剪记录不能还原业务原值。@return 布局事实。"""
    folded, first = console(width=4)
    folded.print('茶tea')
    clipped, second = console(width=8, record=True)
    clipped.print('ABCDEFGHIJK', no_wrap=True, overflow='ellipsis')
    exported = clipped.export_text()
    return {'display_width_differs_from_character_count': len('茶tea') == 4 and cell_len('茶tea') == 5
            and first.getvalue().splitlines() == ['茶te', 'a'],
        'recorded_rendering_does_not_restore_cropped_identifier': 'ABCDEFGHIJK' not in second.getvalue()
            and '…' in second.getvalue() and exported == second.getvalue()}


def capture_and_exports() -> dict:
    """核局部捕获和record导出是两个真实缓冲机制。@return 缓冲事实。"""
    captured, first = console()
    with captured.capture() as capture:
        captured.print('captured')
    requires_record = False
    try:
        captured.export_text()
    except AssertionError:
        requires_record = True
    recorded, _ = console(record=True)
    recorded.print('invoice-marker')
    text = recorded.export_text()
    html_after_clear = recorded.export_html()
    shared, _ = console(record=True)
    shared.print('<invoice>')
    retained = shared.export_text(clear=False)
    html_retained = shared.export_html(clear=False)
    final = shared.export_text()
    empty = shared.export_text()
    return {'capture_returns_local_output_without_enabling_record': capture.get() == 'captured\n'
            and first.getvalue() == '' and requires_record,
        'default_text_export_clears_later_artifact_content': text == 'invoice-marker\n'
            and 'invoice-marker' not in html_after_clear,
        'multiple_exports_can_share_an_explicit_record_lifetime': retained == final == '<invoice>\n'
            and '&lt;invoice&gt;' in html_retained and empty == ''}


def diagnostics() -> dict:
    """仅用合成异常消息说明隐藏locals不能等同整段日志清洗。@return 诊断事实。"""
    rendered, stream = console(width=100)
    try:
        raise ValueError('synthetic-message-marker')
    except ValueError:
        rendered.print_exception(show_locals=False, extra_lines=0, width=100)
    return {'hiding_locals_does_not_redact_exception_message': 'synthetic-message-marker' in stream.getvalue()
        and 'ValueError' in stream.getvalue()}


def main() -> None:
    """核候选归属并输出当前任务事实。@return None。"""
    entries = {'RH-C01': (literal_fields, ['literal_text_requires_explicit_markup_ownership']),
        'RH-U01': (terminal_styles, ['no_color_can_keep_non_color_terminal_styles']),
        'RH-C02': (narrow_reports, ['display_width_differs_from_character_count', 'recorded_rendering_does_not_restore_cropped_identifier']),
        'RH-U02': (capture_and_exports, ['capture_returns_local_output_without_enabling_record']),
        'RH-P01': (capture_and_exports, ['default_text_export_clears_later_artifact_content', 'multiple_exports_can_share_an_explicit_record_lifetime']),
        'RH-P02': (diagnostics, ['hiding_locals_does_not_redact_exception_message'])}
    observe, fields = entries[sys.argv[1]]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(rich.__file__).resolve() == root / 'library/rich/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
