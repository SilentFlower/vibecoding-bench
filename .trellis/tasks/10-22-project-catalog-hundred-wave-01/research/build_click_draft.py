"""制作Click真实工具命令任务，范围来自逐仓固定源码与业务设计。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项独立命令行任务。@return None。"""
    materials = {
        'materials/order-command.py': '''import json
import click

@click.command()
@click.option("--tag", multiple=True)
@click.option("--mode", type=click.Choice(["dev", "prod"], case_sensitive=False), default="dev")
@click.option("--copies", type=click.IntRange(1, 5), default=1)
def ship(tag, mode, copies):
    """输出实际参数。@param tag 标签。@param mode 模式。@param copies 数量。@return None。"""
    click.echo(json.dumps({"tag": tag, "mode": mode, "copies": copies}))

if __name__ == "__main__":
    ship()
''',
        'materials/argument-events.md': 'Compare --tag coffee --tag tea --mode PROD --copies 2, --tag coffee,tea, no tag options, and --copies 0. A separate batch command wants multiple positional file names; distinguish a repeated option from Argument(nargs=-1). No external service or actual file access is needed for these parameter examples.\n',
        'materials/source-command.py': '''import click

@click.command()
@click.option("--copies", type=int, default=1, envvar="VB_CASE_COPIES")
@click.pass_context
def ship(ctx, copies):
    """输出值和来源。@param ctx 上下文。@param copies 数量。@return None。"""
    source = ctx.get_parameter_source("copies")
    click.echo((copies, source.name if source is not None else None))
''',
        'materials/source-events.md': 'Compare direct CLI --copies 4 with environment VB_CASE_COPIES=3 and default_map={"copies":2}; then remove each stronger source in order, ending with the declared default 1. These are synthetic values. A newly created Context before any parse has no recorded copies source; do not relabel an unknown Python invocation as command-line input.\n',
        'materials/output-policy.md': 'A local report command uses click.Path(exists=False, dir_okay=False, path_type=pathlib.Path). Test both an already existing ordinary file and a new path. The application wants an explicit choice between refusing overwrite and replacing an existing result atomically. Explain races between a path check and creation, exclusive x creation, temporary publication and failure cleanup. A path type alone is not a transaction or an exclusive-create guarantee. Do not implement changes.\n',
        'materials/error-notes.py': '''import click
from click.testing import CliRunner

@click.command()
def ship():
    """抛出带本地补救信息的合成错误。@return None。"""
    error = click.ClickException("Order unavailable")
    error.add_note("Check local input")
    error.add_note("咖啡\\nsecond line")
    raise error

result = CliRunner().invoke(ship)
print(result.exit_code)
print(result.stderr)
''',
        'materials/notes-contract.md': 'Enhance controlled error display for both ClickException.show and UsageError.show. After the primary error, emit each nonempty __notes__ string in original order, with exactly one "Note: " prefix per note and preserved internal newlines/Unicode. Ignore empty-string notes. Preserve explicit output streams, current echo color handling, exit codes 1/2, usage/help text appearing once, and byte-identical output when no notes are present. Do not add a traceback or alter format_message. Use an absence-safe notes lookup so Python versions without native add_note remain compatible. Only library/src/click/exceptions.py and the new public regression file library/tests/test_exceptions/test_click_exception.py may change. Add meaningful original-failing public tests for both base and usage errors, and preserve the complete frozen original suite and test controls.\n'}
    definitions = [
        ('CK-U01', 'understand', '解释重复标签、Choice与范围转换',
            'Trace the supplied order command and invocation events. Explain repeated tag values, no-tag defaults, case-insensitive Choice normalization and IntRange failure/exit behavior. Do not edit files.',
            ['materials/order-command.py', 'materials/argument-events.md'], 'explained',
            'Explain the real tuple of repeated tags, canonical prod choice and typed copies value, with exit code 2 on out-of-range input. Do not claim comma-separated tokens are split automatically.', ['repeat_choice_range_observed', 'range_error_rejected']),
        ('CK-C01', 'consult', '选择已有重复选项和变长位置参数',
            'Recommend an existing parameter design for repeated tags and a separate batch of positional files. Explain why a literal comma does not split a tag and how multiple=True differs from Argument(nargs=-1) and unsupported variadic options. Decide whether a library change is needed.',
            ['materials/order-command.py', 'materials/argument-events.md'], 'advice_no_code_change',
            'Use existing multiple=True for repeated option tokens and nargs=-1 for a variadic positional argument, without changing Option arity rules or inventing implicit comma parsing. A library modification is unnecessary for these needs.', ['comma_not_implicit_split', 'variadic_argument_distinct']),
        ('CK-U02', 'understand', '核对四层参数值与来源',
            'Trace the supplied source command and removal sequence. Give the selected value and ParameterSource for CLI, environment, default_map and declared default. Distinguish actual provenance from equality to a default. Do not edit files.',
            ['materials/source-command.py', 'materials/source-events.md'], 'explained',
            'Explain the observed precedence and exact COMMANDLINE, ENVIRONMENT, DEFAULT_MAP and DEFAULT provenance. A value equal to a default is not proof it came from that default.', ['actual_parameter_sources']),
        ('CK-C02', 'consult', '用已有接口解释来源并保留未知',
            'Recommend how the supplied application can report the source of a directly parsed parameter using existing APIs. Explain what to do when Context has no recorded source, including Python-level invocation limits, without inventing provenance or rewriting parsing.',
            ['materials/source-command.py', 'materials/source-events.md'], 'advice_with_limits',
            'Use get_parameter_source for actual recorded direct parsing and preserve None as unknown when no record exists. Do not pretend arbitrary Python invoke/forward calls are command-line input or claim the pinned source has a new INVOCATION source.', ['actual_parameter_sources', 'unknown_source_remains_unknown']),
        ('CK-C03', 'consult', '澄清exists=False与禁止覆盖的区别',
            'Assess the supplied output path policy. Does click.Path(exists=False) mean a destination must not exist? Explain actual behavior for existing and new paths and recommend an application boundary without changing the documented path meaning.',
            ['materials/output-policy.md'], 'advice_no_code_change',
            'Explain that exists=False removes an existence requirement and still accepts an existing valid file. It is not must_not_exist or exclusive creation; retain the existing public meaning and propose an explicit application policy.', ['exists_false_allows_existing']),
        ('CK-P01', 'plan', '规划拒绝覆盖和原子结果发布',
            'Plan the local report output workflow under the supplied policy. Separate path validation, exclusive creation versus intentional replacement, atomic publication, race boundaries and cleanup. Use existing Click/Python APIs without implementing a library change.',
            ['materials/output-policy.md'], 'viable_plan_no_library_change',
            'Give a workable explicit policy: x/exclusive creation for no-overwrite, or a validated temporary result and deliberate atomic replacement when replacement is allowed. A pre-check alone is racy and atomic replacement alone does not mean no-overwrite. Do not promise transactions or invent a Click must_not_exist API.', ['exists_false_allows_existing', 'exclusive_creation_is_distinct']),
        ('CK-D01', 'diagnose', '定位CLI错误附注未显示的边界',
            'Use the complete supplied error-note reproduction. Explain why the command exits with the normal error status but the attached notes do not appear. Locate the actual controlled display boundary and distinguish an output enhancement from failed argument parsing. Do not edit files.',
            ['materials/error-notes.py'], 'diagnosed',
            'Ground the diagnosis in ClickException.show/UsageError.show emitting formatted main messages without __notes__. add_note attaches Python exception metadata but does not automatically extend these controlled displays; preserve the valid exit behavior.', ['original_notes_not_displayed', 'exit_codes_preserved']),
        ('CK-M01', 'modify', '展示有序错误附注并保护既有CLI输出',
            'Implement the complete public note-display enhancement for both base and usage errors. Preserve streams, color, unnoted output, usage, exit codes and format_message. Modify only the authorized implementation and new public test file, with meaningful original-failing tests.',
            ['materials/error-notes.py', 'materials/notes-contract.md'], 'implemented',
            'Satisfy the complete declared note order/prefix/empty/Unicode contract on ClickException and UsageError, preserving ordinary output, color, streams, usage and exit codes. Do not move notes into format_message or modify original tests/controls; complete frozen original regression must pass.', ['basic_notes_in_order', 'usage_notes_in_order', 'exit_codes_preserved', 'unnoted_output_preserved', 'format_message_unchanged', 'explicit_stream_and_color_preserved'])]
    scenes = [('CK-S01', '批处理命令的参数设计', '用已有参数类型表达标签和文件批次', ['CK-U01', 'CK-C01']),
        ('CK-S02', '参数配置与真实来源', '解释实际来源并保留未知状态', ['CK-U02', 'CK-C02']),
        ('CK-S03', '本地报告输出策略', '区分路径验证、拒绝覆盖和原子发布', ['CK-C03', 'CK-P01']),
        ('CK-S04', '可操作的命令错误信息', '定位并增强受控错误附注输出', ['CK-D01', 'CK-M01'])]
    build_project('click', {'title': 'Click工具命令工作场景', 'category': '命令参数与应用交互',
        'description': '固定真实源码上的批处理参数、配置来源、文件发布和错误附注增强；四场景八任务。'},
        definitions, scenes, materials,
        modifications={'CK-M01': ['library/src/click/exceptions.py', 'library/tests/test_exceptions/test_click_exception.py']},
        extra_entries={'CK-S04': [{'id': 'diagnose_only', 'task_ids': ['CK-D01']},
            {'id': 'modify_direct', 'task_ids': ['CK-M01']}]})


if __name__ == '__main__':
    main()
