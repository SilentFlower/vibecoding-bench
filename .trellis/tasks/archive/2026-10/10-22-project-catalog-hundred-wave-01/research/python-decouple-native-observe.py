"""用合成配置文件观察真实优先级、快照、编码和列表转换。"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import decouple
from decouple import Choices, Config, Csv, RepositoryEnv, UndefinedValueError


def rejects(function, exception: type[Exception]) -> bool:
    """核明确错误而非吞掉异常。@param function 调用。@param exception 异常类。@return 是否拒绝。"""
    try:
        function()
    except exception:
        return True
    return False


def configuration_observations() -> dict:
    """观察实际文件、环境优先级与转换失败。@return 合成配置事实。"""
    with tempfile.TemporaryDirectory(prefix='decouple-startup-') as directory:
        source = Path(directory) / '.env'
        source.write_text('VB_CASE_PORT=8000\nVB_CASE_EMPTY=file\nVB_CASE_DEBUG=False\nVB_CASE_MODE=prod\n', encoding='utf-8')
        with patch.dict(os.environ, {'VB_CASE_PORT': '9000', 'VB_CASE_EMPTY': ''}):
            config = Config(RepositoryEnv(str(source)))
            precedence = config('VB_CASE_PORT', default='7000') == '9000'
            empty = config('VB_CASE_EMPTY', default='fallback') == ''
            fallback = config('VB_CASE_NEVER_DEFINED', default=42, cast=int) == 42
            missing = rejects(lambda: config('VB_CASE_NEVER_DEFINED'), UndefinedValueError)
            boolean = config('VB_CASE_DEBUG', cast=bool) is False
            choices = config('VB_CASE_MODE', cast=Choices(['dev', 'prod'])) == 'prod'
            with patch.dict(os.environ, {'VB_CASE_PORT': '', 'VB_CASE_MODE': 'invalid'}):
                errors = rejects(lambda: config('VB_CASE_PORT', default=7000, cast=int), ValueError)
                errors = errors and rejects(lambda: config('VB_CASE_MODE', default='dev',
                    cast=Choices(['dev', 'prod'])), ValueError)
            return {'environment_file_default_order': precedence and fallback and missing,
                'empty_environment_wins': empty, 'existing_casts_observed': boolean and choices,
                'cast_errors_not_fallback': errors}


def reload_observations() -> dict:
    """区分文件构造快照和每次环境读取。@return 重载边界。"""
    with tempfile.TemporaryDirectory(prefix='decouple-reload-') as directory:
        source = Path(directory) / '.env'
        source.write_text('VB_CASE_LABEL=first\n', encoding='utf-8')
        old = Config(RepositoryEnv(str(source)))
        first = old('VB_CASE_LABEL')
        source.write_text('VB_CASE_LABEL=second\n', encoding='utf-8')
        stale = old('VB_CASE_LABEL')
        fresh = Config(RepositoryEnv(str(source)))('VB_CASE_LABEL')
        with patch.dict(os.environ, {'VB_CASE_LABEL': 'environment-one'}):
            one = old('VB_CASE_LABEL')
            os.environ['VB_CASE_LABEL'] = 'environment-two'
            two = old('VB_CASE_LABEL')
        return {'file_repository_is_snapshot': first == stale == 'first' and fresh == 'second',
            'environment_reads_remain_dynamic': [one, two] == ['environment-one', 'environment-two']}


def dialect_observations() -> dict:
    """核文件首BOM和简单ENV语法的实际行为。@return 编码和语法事实。"""
    with tempfile.TemporaryDirectory(prefix='decouple-encoding-') as directory:
        source = Path(directory) / '.env'
        source.write_text('\ufeffVB_CASE_TITLE=咖啡\nVB_CASE_INSIDE=a\ufeffb\n', encoding='utf-8')
        ordinary = RepositoryEnv(str(source))
        explicit = RepositoryEnv(str(source), encoding='utf-8-sig')
        bom = ('VB_CASE_TITLE' not in ordinary.data and '\ufeffVB_CASE_TITLE' in ordinary.data
            and explicit.data['VB_CASE_TITLE'] == '咖啡' and explicit.data['VB_CASE_INSIDE'] == 'a\ufeffb')
        source.write_text('export VB_CASE_EXPORT=value\nVB_CASE_HASH=a#b\nVB_CASE_EQUALS=a=b\nVB_CASE_QUOTED="coffee beans"\n', encoding='utf-8')
        parsed = RepositoryEnv(str(source)).data
        return {'existing_encoding_handles_bom': bom,
            'simple_env_dialect_observed': parsed == {'export VB_CASE_EXPORT': 'value',
                'VB_CASE_HASH': 'a#b', 'VB_CASE_EQUALS': 'a=b', 'VB_CASE_QUOTED': 'coffee beans'}}


def list_observations() -> dict:
    """实测shlex与真正CSV的差别，并复用已有callable cast。@return 字段保真事实。"""
    config = Config({'VB_CASE_LIST': r'coffee#roast,,\d+'})
    literal = config('VB_CASE_LIST', cast=lambda value: next(csv.reader([value], strict=True)))
    return {'shlex_comment_and_escape_observed': Csv()('coffee#roast,tea') == ['coffee']
            and Csv()(r'\d+,tea') == ['d+', 'tea'],
        'csv_helper_drops_empty_fields': Csv()('coffee,,tea') == ['coffee', 'tea'],
        'quoted_comma_and_postprocess': Csv()('"coffee, beans",tea') == ['coffee, beans', 'tea']
            and Csv(cast=int, post_process=tuple)('1, 2') == (1, 2),
        'existing_callable_cast_preserves_fields': literal == ['coffee#roast', '', r'\d+']}


def main() -> None:
    """输出当前只读任务的实际事实。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    fields = {'DC-U01': ('environment_file_default_order', 'empty_environment_wins'),
        'DC-C01': ('existing_casts_observed', 'cast_errors_not_fallback'),
        'DC-P01': ('environment_file_default_order', 'existing_casts_observed', 'cast_errors_not_fallback'),
        'DC-C02': ('file_repository_is_snapshot', 'environment_reads_remain_dynamic'),
        'DC-U02': ('existing_encoding_handles_bom',),
        'DC-C03': ('simple_env_dialect_observed',),
        'DC-U03': ('shlex_comment_and_escape_observed', 'csv_helper_drops_empty_fields', 'quoted_comma_and_postprocess'),
        'DC-C04': ('existing_callable_cast_preserves_fields',)}
    if task in ('DC-U01', 'DC-C01', 'DC-P01'):
        facts = configuration_observations()
    elif task == 'DC-C02':
        facts = reload_observations()
    elif task in ('DC-U02', 'DC-C03'):
        facts = dialect_observations()
    else:
        facts = list_observations()
    print(json.dumps({'candidate_import': Path(decouple.__file__).resolve() == root / 'library/decouple.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
