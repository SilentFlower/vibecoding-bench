"""观察真实Markdown入口、AST、规范化和CLI空文档副作用。"""
from __future__ import annotations

import json
import os
import pty
import subprocess
import sys
import tempfile
from pathlib import Path

import mistune
from mistune import create_markdown, markdown
from mistune.renderers.markdown import MarkdownRenderer


DOCUMENT = 'A ~~old~~ item.\n\n<b>商品</b>\n\n| Name | Qty |\n|---|---|\n|coffee|2|\n'


def configuration_observations() -> dict:
    """对照真实默认和明确配置，顺序复用独立文档。@return 实际渲染事实。"""
    ordinary = markdown(DOCUMENT)
    convenient = mistune.html(DOCUMENT)
    configured = create_markdown(escape=True, plugins=['strikethrough', 'table'])
    explicit = configured(DOCUMENT)
    first = configured('# First only')
    second = configured('# Second only')
    return {'different_entry_defaults_observed': '&lt;b&gt;商品&lt;/b&gt;' in ordinary
            and '<b>商品</b>' in convenient and '<table>' not in ordinary
            and '<table>' in convenient and '<del>old</del>' in convenient,
        'existing_explicit_configuration': '<table>' in explicit and '<del>old</del>' in explicit
            and '&lt;b&gt;商品&lt;/b&gt;' in explicit,
        'sequential_document_state_distinct': 'First only' in first and 'Second only' in second
            and 'First only' not in second}


def ast_observations() -> dict:
    """实际序列化API token，并与CLI现有文本输出路径对照。@return AST边界。"""
    tokens = markdown('# 咖啡\n\nCoffee **beans**.', renderer='ast')
    encoded = json.dumps(tokens, ensure_ascii=False)
    cli = subprocess.run([sys.executable, '-m', 'mistune', '-r', 'ast', '-m', '# 咖啡'],
        text=True, capture_output=True, timeout=8)
    return {'structured_ast_is_json_serializable': isinstance(tokens, list)
            and json.loads(encoded) == tokens and '咖啡' in encoded and 'beans' in encoded,
        'cli_ast_not_serialized_original': cli.returncode != 0 and 'AssertionError' in cli.stderr}


def empty_observations() -> dict:
    """用真实管道、文件和PTY核None与空文档分派。@return CLI行为矩阵。"""
    def run(arguments, text=''):
        """执行候选CLI。@param arguments 参数。@param text 管道正文。@return 进程结果。"""
        return subprocess.run([sys.executable, '-m', 'mistune', *arguments],
            input=text, text=True, capture_output=True, timeout=8)

    with tempfile.TemporaryDirectory(prefix='mistune-empty-') as directory:
        root = Path(directory)
        empty, nonempty = root / 'empty.md', root / 'document.md'
        empty.write_text('', encoding='utf-8')
        nonempty.write_text('# File fallback', encoding='utf-8')
        pipe = run([])
        message = run(['-m', ''])
        file = run(['-f', str(empty)])
        destination = root / 'result.html'
        output = run(['-m', '', '-o', str(destination)])
        priority = run(['-m', '', '-f', str(nonempty)])
        normal = run(['-m', '0'])
        missing = run(['-f', str(root / 'missing.md')])
        master, slave = pty.openpty()
        try:
            terminal = subprocess.run([sys.executable, '-m', 'mistune'], stdin=slave,
                text=True, capture_output=True, timeout=8)
        finally:
            os.close(master)
            os.close(slave)
        return {'original_empty_dispatch_gap': pipe.returncode == message.returncode == 1
                and 'You must specify' in pipe.stdout and file.returncode == 0,
            'api_empty_document_valid': markdown('') == '',
            'pipe_and_message_empty_valid': pipe.returncode == message.returncode == 0
                and pipe.stdout.strip() == message.stdout.strip() == '',
            'empty_file_preserved': file.returncode == 0 and file.stdout.strip() == '',
            'explicit_empty_output_file_written': output.returncode == 0 and destination.is_file()
                and destination.read_text() == '' and output.stdout == '',
            'explicit_empty_message_has_priority': priority.returncode == 0 and priority.stdout.strip() == '',
            'nonempty_and_missing_preserved': normal.returncode == 0 and '<p>0</p>' in normal.stdout
                and missing.returncode != 0,
            'interactive_absence_does_not_block': terminal.returncode == 1 and 'You must specify' in terminal.stdout}


def normalization_observations() -> dict:
    """用实际强标记规范化区分语义和原始字节。@return 重排事实。"""
    original = 'Coffee __beans__.\n'
    rewritten = create_markdown(renderer=MarkdownRenderer())(original)
    return {'markdown_renderer_normalizes_source': rewritten != original and '**beans**' in rewritten
            and markdown(rewritten) == markdown(original)}


def main() -> None:
    """输出冻结任务的实际事实。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    selected = {'MS-U01': ('different_entry_defaults_observed',),
        'MS-C01': ('existing_explicit_configuration',),
        'MS-P01': ('existing_explicit_configuration', 'sequential_document_state_distinct'),
        'MS-U02': ('structured_ast_is_json_serializable',),
        'MS-C02': ('structured_ast_is_json_serializable', 'cli_ast_not_serialized_original'),
        'MS-D01': ('original_empty_dispatch_gap', 'api_empty_document_valid'),
        'MS-M01': ('pipe_and_message_empty_valid', 'empty_file_preserved', 'explicit_empty_output_file_written',
            'explicit_empty_message_has_priority', 'nonempty_and_missing_preserved', 'interactive_absence_does_not_block'),
        'MS-C03': ('markdown_renderer_normalizes_source',)}
    if task in ('MS-U01', 'MS-C01', 'MS-P01'):
        facts = configuration_observations()
    elif task in ('MS-U02', 'MS-C02'):
        facts = ast_observations()
    elif task in ('MS-D01', 'MS-M01'):
        facts = empty_observations()
    else:
        facts = normalization_observations()
    print(json.dumps({'candidate_import': Path(mistune.__file__).resolve() == root / 'library/src/mistune/__init__.py',
        **{field: facts[field] for field in selected[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
