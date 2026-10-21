"""通过真实Click调用核参数、来源、文件与错误输出，不匹配模型措辞。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from io import StringIO
from pathlib import Path

import click
from click.testing import CliRunner


def option_observations() -> dict:
    """直接解析重复选项、范围和变长参数。@return 参数事实。"""
    @click.command()
    @click.option('--tag', multiple=True)
    @click.option('--mode', type=click.Choice(['dev', 'prod'], case_sensitive=False), default='dev')
    @click.option('--copies', type=click.IntRange(1, 5), default=1)
    def ship(tag, mode, copies):
        """返回实际解析值。@param tag 标签。@param mode 模式。@param copies 数量。@return None。"""
        click.echo(json.dumps({'tag': tag, 'mode': mode, 'copies': copies}))

    @click.command()
    @click.argument('files', nargs=-1)
    def collect(files):
        """读取变长位置参数。@param files 文件参数。@return None。"""
        click.echo(json.dumps(list(files)))

    runner = CliRunner()
    normal = runner.invoke(ship, ['--tag', 'coffee', '--tag', 'tea', '--mode', 'PROD', '--copies', '2'])
    single = runner.invoke(ship, ['--tag', 'coffee,tea'])
    rejected = runner.invoke(ship, ['--copies', '0'])
    positional = runner.invoke(collect, ['a.txt', 'b.txt'])
    try:
        click.Option(['--files'], nargs=-1)
    except TypeError:
        option_arity_rejected = True
    else:
        option_arity_rejected = False
    return {'repeat_choice_range_observed': normal.exit_code == 0 and json.loads(normal.stdout) == {
            'tag': ['coffee', 'tea'], 'mode': 'prod', 'copies': 2},
        'range_error_rejected': rejected.exit_code == 2 and '0' in rejected.stderr,
        'comma_not_implicit_split': single.exit_code == 0 and json.loads(single.stdout)['tag'] == ['coffee,tea'],
        'variadic_argument_distinct': positional.exit_code == 0 and json.loads(positional.stdout) == ['a.txt', 'b.txt']
            and option_arity_rejected}


def source_observations() -> dict:
    """实际比较四种解析来源，未知Python调用来源继续保留未知。@return 来源事实。"""
    @click.command()
    @click.option('--copies', type=int, default=1, envvar='VB_CASE_COPIES')
    @click.pass_context
    def ship(ctx, copies):
        """输出实际值及来源。@param ctx 上下文。@param copies 数量。@return None。"""
        source = ctx.get_parameter_source('copies')
        click.echo(json.dumps([copies, source.name if source is not None else None]))

    runner = CliRunner()
    cases = [(['--copies', '4'], {'VB_CASE_COPIES': '3'}, {'copies': 2}),
        ([], {'VB_CASE_COPIES': '3'}, {'copies': 2}),
        ([], {'VB_CASE_COPIES': None}, {'copies': 2}),
        ([], {'VB_CASE_COPIES': None}, {})]
    actual = []
    for arguments, environment, defaults in cases:
        result = runner.invoke(ship, arguments, env=environment, default_map=defaults)
        actual.append(json.loads(result.stdout) if result.exit_code == 0 else None)
    return {'actual_parameter_sources': actual == [[4, 'COMMANDLINE'], [3, 'ENVIRONMENT'],
            [2, 'DEFAULT_MAP'], [1, 'DEFAULT']],
        'unknown_source_remains_unknown': click.Context(click.Command('ship')).get_parameter_source('copies') is None}


def path_observations() -> dict:
    """核路径预检与真正排他创建的差别。@return 文件副作用事实。"""
    with tempfile.TemporaryDirectory(prefix='click-output-') as directory:
        existing, missing = Path(directory) / 'existing.txt', Path(directory) / 'new.txt'
        existing.write_text('original', encoding='utf-8')
        kind = click.Path(exists=False, dir_okay=False, path_type=Path)
        accepted = kind.convert(str(existing), None, None) == existing
        accepted = accepted and kind.convert(str(missing), None, None) == missing
        try:
            existing.open('x', encoding='utf-8')
        except FileExistsError:
            protected = existing.read_text() == 'original'
        else:
            protected = False
        with missing.open('x', encoding='utf-8') as stream:
            stream.write('new result')
        return {'exists_false_allows_existing': accepted,
            'exclusive_creation_is_distinct': protected and missing.read_text() == 'new result'}


def error_observations() -> dict:
    """观察原版附注缺口及增强后的受控输出，保留退出和色彩。@return 错误矩阵。"""
    def run(kind: str, notes: bool):
        """运行真实抛错命令。@param kind 错误类。@param notes 是否有附注。@return 原生结果。"""
        @click.command()
        def ship():
            """抛出合成错误。@return None。"""
            error = (click.ClickException('Order unavailable') if kind == 'basic'
                else click.UsageError('Invalid order', ctx=click.get_current_context()))
            if notes:
                error.add_note('Check local input')
                error.add_note('')
                error.add_note('咖啡\nsecond line')
            raise error

        return CliRunner().invoke(ship)

    basic, usage = run('basic', True), run('usage', True)
    control, usage_control = run('basic', False), run('usage', False)
    expected_notes = 'Note: Check local input\nNote: 咖啡\nsecond line\n'
    with click.Context(click.Command('ship'), color=False):
        error = click.ClickException('Order unavailable')
        error.add_note('\x1b[31mcoffee\x1b[0m')
    output = StringIO()
    error.show(file=output)
    return {'original_notes_not_displayed': 'Note:' not in basic.stderr and 'Note:' not in usage.stderr
            and 'Check local input' not in basic.stderr and 'Check local input' not in usage.stderr,
        'basic_notes_in_order': basic.stderr == 'Error: Order unavailable\n' + expected_notes,
        'usage_notes_in_order': usage.stderr.endswith('Error: Invalid order\n' + expected_notes)
            and usage.stderr.count('Usage:') == 1,
        'exit_codes_preserved': basic.exit_code == control.exit_code == 1
            and usage.exit_code == usage_control.exit_code == 2,
        'unnoted_output_preserved': control.stderr == 'Error: Order unavailable\n'
            and usage_control.stderr.count('Usage:') == 1 and usage_control.stderr.endswith('Error: Invalid order\n'),
        'format_message_unchanged': error.format_message() == 'Order unavailable',
        'explicit_stream_and_color_preserved': output.getvalue() == 'Error: Order unavailable\nNote: coffee\n'}


def main() -> None:
    """输出当前任务的实际原生事实。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    selected = {'CK-U01': ('repeat_choice_range_observed', 'range_error_rejected'),
        'CK-C01': ('comma_not_implicit_split', 'variadic_argument_distinct'),
        'CK-U02': ('actual_parameter_sources',),
        'CK-C02': ('actual_parameter_sources', 'unknown_source_remains_unknown'),
        'CK-C03': ('exists_false_allows_existing',),
        'CK-P01': ('exists_false_allows_existing', 'exclusive_creation_is_distinct'),
        'CK-D01': ('original_notes_not_displayed', 'exit_codes_preserved'),
        'CK-M01': ('basic_notes_in_order', 'usage_notes_in_order', 'exit_codes_preserved',
            'unnoted_output_preserved', 'format_message_unchanged', 'explicit_stream_and_color_preserved')}
    if task in ('CK-U01', 'CK-C01'):
        facts = option_observations()
    elif task in ('CK-U02', 'CK-C02'):
        facts = source_observations()
    elif task in ('CK-C03', 'CK-P01'):
        facts = path_observations()
    else:
        facts = error_observations()
    print(json.dumps({'candidate_import': Path(click.__file__).resolve() == root / 'library/src/click/__init__.py',
        **{field: facts[field] for field in selected[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
