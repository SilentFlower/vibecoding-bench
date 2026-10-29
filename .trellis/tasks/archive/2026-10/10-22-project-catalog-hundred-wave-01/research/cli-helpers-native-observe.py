"""观察真实显示、CSV/JSONL、默认选项隔离和一次性行输入。"""
from __future__ import annotations

import csv
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import cli_helpers
from cli_helpers.tabular_output import TabularOutputFormatter, format_output


def export_observations() -> dict:
    """独立解析实际CSV/JSONL，不把排版字符串当交换格式。@return 数据导出事实。"""
    rows = [['coffee, beans', None], ['咖啡', 2]]
    headers = ['product', 'quantity']
    saved = [list(row) for row in rows]
    csv_lines = list(format_output(rows, headers, format_name='csv'))
    json_lines = list(format_output(rows, headers, format_name='jsonl'))
    display = '\n'.join(format_output(rows, headers, format_name='simple'))
    return {'csv_quotes_and_missing': list(csv.reader(csv_lines)) == [headers,
            ['coffee, beans', ''], ['咖啡', '2']],
        'jsonl_retains_unicode_and_null': [json.loads(line) for line in json_lines] == [
            {'product': 'coffee, beans', 'quantity': None}, {'product': '咖啡', 'quantity': 2}]
            and '咖啡' in json_lines[1],
        'display_missing_marker': '<null>' in display,
        'source_records_unchanged': rows == saved}


def json_boundary_observations() -> dict:
    """核同名列与Decimal现有限制，并验证应用兼容策略。@return 实际JSON事实。"""
    duplicate = json.loads(next(iter(format_output([[1, 2]], ['id', 'id'], format_name='jsonl'))))
    value = Decimal('0.12345678901234567890123456789')
    numeric = next(iter(format_output([[value]], ['price'], format_name='jsonl')))
    parsed = json.loads(numeric, parse_float=Decimal)
    protected = json.loads(next(iter(format_output([[str(value)]], ['price'], format_name='jsonl'))))
    headers = ['id', 'id']
    return {'duplicate_header_last_value': duplicate == {'id': 2},
        'decimal_numeric_output_not_exact': parsed['price'] != value,
        'application_unique_header_check': len(set(headers)) != len(headers),
        'existing_string_preformat_preserves_decimal': protected['price'] == str(value)}


def option_observations() -> dict:
    """实际调用内置和自定义格式，核注册与调用方默认不受污染。@return 隔离矩阵。"""
    cls = TabularOutputFormatter
    registry = cls._output_formats
    cls._output_formats = {key: row._replace(formatter_args=dict(row.formatter_args))
        for key, row in registry.items()}
    try:
        default = cls._output_formats['simple'].formatter_args['missing_value']
        pending = cls('simple').format_output([[None]], ['value'], missing_value='N/A')
        second = '\n'.join(cls('simple').format_output([[None]], ['value'], missing_value='EMPTY'))
        first = '\n'.join(pending)
        final = '\n'.join(cls('simple').format_output([[None]], ['value']))
        local = dict(cls._output_formats['simple'].formatter_args)

        def render(data, headers, missing_value='BASE', **kwargs):
            """自定义格式照常接收本次选项。@param data 行。@param headers 表头。@param missing_value 缺值。@param kwargs 其他选项。@return 行迭代器。"""
            return iter([missing_value])

        supplied = {'missing_value': 'BASE'}
        cls.register_new_formatter('bench_custom', render, kwargs=supplied)
        custom_first = list(cls('bench_custom').format_output([[None]], ['value'], missing_value='CUSTOM'))
        custom_second = list(cls('bench_custom').format_output([[None]], ['value']))
        return {'original_default_leak_observed': default not in final and 'EMPTY' in final
                and local['missing_value'] == 'EMPTY',
            'builtin_defaults_isolated': 'N/A' in first and 'EMPTY' in second and default in final
                and local['missing_value'] == default,
            'custom_defaults_isolated': custom_first == ['CUSTOM'] and custom_second == ['BASE'],
            'caller_default_mapping_unchanged': supplied == {'missing_value': 'BASE'}}
    finally:
        cls._output_formats = registry


def row_iterator_observations() -> dict:
    """对照一次性行生成器与有限行显式固定。@return 真实消费事实。"""
    values = [['coffee', 2], ['tea', 3]]
    headers = ['product', 'quantity']
    unstable = list(format_output((iter(row) for row in values), headers, format_name='csv'))
    stabilized = list(format_output([list(row) for row in values], headers, format_name='csv'))
    return {'one_shot_rows_are_consumed': list(csv.reader(unstable)) != [headers, ['coffee', '2'], ['tea', '3']],
        'bounded_row_materialization_works': list(csv.reader(stabilized)) == [headers, ['coffee', '2'], ['tea', '3']]}


def main() -> None:
    """输出当前任务冻结的业务观察。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    selected = {'CH-U01': ('csv_quotes_and_missing', 'jsonl_retains_unicode_and_null', 'display_missing_marker'),
        'CH-C01': ('csv_quotes_and_missing', 'jsonl_retains_unicode_and_null'),
        'CH-P01': ('csv_quotes_and_missing', 'jsonl_retains_unicode_and_null', 'source_records_unchanged'),
        'CH-D01': ('duplicate_header_last_value', 'decimal_numeric_output_not_exact'),
        'CH-C02': ('application_unique_header_check', 'existing_string_preformat_preserves_decimal'),
        'CH-D02': ('original_default_leak_observed',),
        'CH-M01': ('builtin_defaults_isolated', 'custom_defaults_isolated', 'caller_default_mapping_unchanged'),
        'CH-C03': ('one_shot_rows_are_consumed', 'bounded_row_materialization_works')}
    if task in ('CH-U01', 'CH-C01', 'CH-P01'):
        facts = export_observations()
    elif task in ('CH-D01', 'CH-C02'):
        facts = json_boundary_observations()
    elif task in ('CH-D02', 'CH-M01'):
        facts = option_observations()
    else:
        facts = row_iterator_observations()
    print(json.dumps({'candidate_import': Path(cli_helpers.__file__).resolve() == root / 'library/cli_helpers/__init__.py',
        **{field: facts[field] for field in selected[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
