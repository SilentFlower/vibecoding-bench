"""独立观察ConfigArgParse优先级、布尔转换、解析格式和配置流。"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import sys

import configargparse
from configargparse import ArgumentParser, DefaultConfigFileParser, IniConfigParser, YAMLConfigFileParser


def workers_parser() -> ArgumentParser:
    """定义明确合成来源，不接触真实命令行或环境。@return 新解析器。"""
    parser = ArgumentParser(add_help=False)
    parser.add_argument('--workers', type=int, default=1, env_var='APP_WORKERS')
    return parser


def sources() -> dict:
    """核来源覆盖和默认来源输出没有自动脱敏。@return 来源事实。"""
    selected = workers_parser().parse_args(['--workers', '4'], config_file_contents='workers=2', env_vars={'APP_WORKERS': '3'})
    environment = workers_parser().parse_args([], config_file_contents='workers=2', env_vars={'APP_WORKERS': '3'})
    configured = workers_parser().parse_args([], config_file_contents='workers=2', env_vars={})
    default = workers_parser().parse_args([], config_file_contents='', env_vars={})
    report = ArgumentParser(add_help=False)
    report.add_argument('--password', env_var='APP_PASSWORD')
    report.parse_args([], env_vars={'APP_PASSWORD': 'synthetic-password'})
    provenance = report.get_source_to_settings_dict()
    text = report.format_values()
    return {'scalar_precedence_is_cli_environment_config_default': [selected.workers, environment.workers,
            configured.workers, default.workers] == [4, 3, 2, 1],
        'source_reporting_keeps_values_and_requires_application_policy': provenance['environment_variables']['APP_PASSWORD'][1]
            == 'synthetic-password' and 'APP_PASSWORD' in text and 'synthetic-password' in text}


def append_values() -> dict:
    """核来源覆盖不等于删除argparse自己的非空默认列表。@return 列表事实。"""
    def parser() -> ArgumentParser:
        """每个比较使用独立默认列表。@return 新解析器。"""
        value = ArgumentParser(add_help=False)
        value.add_argument('--tag', action='append', default=['base'], env_var='APP_TAGS')
        return value

    cli = parser().parse_args(['--tag', 'cli'], config_file_contents='tag=[cfg]', env_vars={'APP_TAGS': '["env1","env2"]'})
    env = parser().parse_args([], config_file_contents='tag=[cfg]', env_vars={'APP_TAGS': '["env1","env2"]'})
    cfg = parser().parse_args([], config_file_contents='tag=[cfg]', env_vars={})
    return {'append_keeps_declared_defaults_but_selects_one_supplied_source': cli.tag == ['base', 'cli']
        and env.tag == ['base', 'env1', 'env2'] and cfg.tag == ['base', 'cfg']}


def boolean_switches() -> dict:
    """核字符串bool与已有布尔action的真实区别。@return 布尔事实。"""
    bad = ArgumentParser(add_help=False)
    bad.add_argument('--enabled', type=bool, env_var='APP_ENABLED')
    approximation = bad.parse_args([], env_vars={'APP_ENABLED': 'false'}).enabled

    def parser() -> ArgumentParser:
        """使用原生无需值的开关action。@return 新解析器。"""
        value = ArgumentParser(add_help=False)
        value.add_argument('--enabled', action='store_true', env_var='APP_ENABLED')
        return value

    disabled = parser().parse_args([], env_vars={'APP_ENABLED': 'false'}).enabled
    enabled = parser().parse_args([], env_vars={'APP_ENABLED': 'true'}).enabled
    cli = parser().parse_args(['--enabled'], env_vars={'APP_ENABLED': 'false'}).enabled
    rejected = False
    with redirect_stderr(StringIO()):
        try:
            parser().parse_args([], env_vars={'APP_ENABLED': 'maybe'})
        except SystemExit as error:
            rejected = error.code == 2
    return {'existing_boolean_action_parses_false_and_rejects_unknown_tokens': approximation is True
        and disabled is False and enabled is True and cli is True and rejected}


def formats() -> dict:
    """核默认格式的节边界和多行表示限制。@return 格式事实。"""
    contents = '[dev]\nhost=A\n[prod]\nhost=B\n'
    flattened = DefaultConfigFileParser().parse(StringIO(contents))
    selected = IniConfigParser(['dev'], split_ml_text_to_list=False).parse(StringIO(contents))
    rejected = False
    default_parser = DefaultConfigFileParser()
    try:
        default_parser.serialize({'message': 'line1\nline2'})
    except ValueError:
        rejected = True
    yaml_parser = YAMLConfigFileParser()
    text = yaml_parser.serialize({'message': 'line1\nline2'})
    return {'default_section_comments_are_not_selected_ini_sections': flattened == {'host': 'B'}
            and selected == {'host': 'A'},
        'multiline_serialization_needs_a_supporting_format': rejected
            and yaml_parser.parse(StringIO(text)) == {'message': 'line1\nline2'}
            and default_parser.parse(StringIO(default_parser.serialize({'workers': '2'}))) == {'workers': '2'}}


def reloadable_provider() -> dict:
    """只用新建内存流核提供者调用和关闭，不访问远程配置。@return 生命周期事实。"""
    streams = []

    def provider():
        """每次返回当前合成配置的新流。@return 新StringIO。"""
        stream = StringIO('workers=' + str(len(streams) + 2))
        streams.append(stream)
        return stream

    parser = ArgumentParser(add_help=False, default_config_files=[provider])
    parser.add_argument('--workers', type=int)
    first = parser.parse_args([], env_vars={}).workers
    closed_after_first = len(streams) == 1 and streams[0].closed
    second = parser.parse_args([], env_vars={}).workers
    return {'callable_provider_reopens_and_parser_closes_each_stream': first == 2 and second == 3
        and closed_after_first and len(streams) == 2 and all(stream.closed for stream in streams)}


def main() -> None:
    """核单文件候选并输出精确expected字段。@return None。"""
    entries = {'CA-U01': (sources, ['scalar_precedence_is_cli_environment_config_default']),
        'CA-C01': (sources, ['source_reporting_keeps_values_and_requires_application_policy']),
        'CA-U02': (append_values, ['append_keeps_declared_defaults_but_selects_one_supplied_source']),
        'CA-C02': (boolean_switches, ['existing_boolean_action_parses_false_and_rejects_unknown_tokens']),
        'CA-U03': (formats, ['default_section_comments_are_not_selected_ini_sections']),
        'CA-C03': (formats, ['multiline_serialization_needs_a_supporting_format']),
        'CA-P01': (reloadable_provider, ['callable_provider_reopens_and_parser_closes_each_stream'])}
    observe, fields = entries[sys.argv[1]]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(configargparse.__file__).resolve() == root / 'library/configargparse.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
