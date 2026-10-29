"""以实际报表、HTML、CLI和序列输出核验Tabulate，不匹配回答措辞。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import tabulate as module
from tabulate import tabulate
from wcwidth import wcswidth


def numeric_observations() -> dict:
    """区分实际数值推断和按列保护，不修改业务输入。@return 报表事实。"""
    rows = [['00123', '2.50'], ['1e3', '3.00']]
    saved = [list(row) for row in rows]
    default = tabulate(rows, headers=['sku', 'price'], tablefmt='plain')
    protected = tabulate(rows, headers=['sku', 'price'], tablefmt='plain', disable_numparse=[0], floatfmt='.2f')
    missing = tabulate([['00123', None]], headers=['sku', 'price'], tablefmt='plain',
        disable_numparse=[0], missingval='N/A')
    return {'numeric_inference_observed': [line.split() for line in default.splitlines()][1:] == [
            ['123', '2.5'], ['1000', '3']],
        'existing_column_policy': [line.split() for line in protected.splitlines()][1:] == [
            ['00123', '2.50'], ['1e3', '3.00']],
        'input_unchanged': rows == saved,
        'missing_value_policy': missing.splitlines()[-1].split() == ['00123', 'N/A']}


def sequence_observations() -> dict:
    """比较不同参数的list/tuple、补齐和输入保真。@return 行为矩阵。"""
    rows = [['coffee\nbeans', 'ready'], ['tea', 'packed']]
    headers = ['Product name', 'Shipping note']
    failures, matches, unchanged = [], [], []
    for name in ('rowalign', 'maxheadercolwidths'):
        values = ['bottom'] if name == 'rowalign' else [6]
        before = list(values)
        original_tuple = tuple(values)
        expected = tabulate(rows, headers=headers, tablefmt='grid', **{name: values})
        try:
            actual = tabulate(rows, headers=headers, tablefmt='grid', **{name: original_tuple})
        except TypeError:
            failures.append(True)
            matches.append(False)
        else:
            failures.append(False)
            matches.append(actual == expected)
        unchanged.append(values == before and original_tuple == tuple(before))
    empty_cases = []
    for name in ('rowalign', 'maxheadercolwidths'):
        try:
            empty_cases.append(tabulate(rows, headers=headers, tablefmt='grid', **{name: ()})
                == tabulate(rows, headers=headers, tablefmt='grid', **{name: []}))
        except TypeError:
            empty_cases.append(False)
    return {'tuple_parameters_rejected_original': all(failures),
        'rowalign_tuple_equivalent': matches[0], 'headerwidth_tuple_equivalent': matches[1],
        'caller_sequences_unchanged': all(unchanged), 'empty_tuple_defaults_preserved': all(empty_cases),
        'ordinary_default_preserved': tabulate([['coffee', 2]], tablefmt='plain').split() == ['coffee', '2']}


def medium_observations() -> dict:
    """对照普通标记文字和中文显示列宽。@return 输出介质事实。"""
    text = '<b>商品</b>'
    escaped = tabulate([[text]], tablefmt='html')
    raw = tabulate([[text]], tablefmt='unsafehtml')
    report = tabulate([['咖啡咖啡咖啡', '长期订阅订单']], headers=['Product', 'Delivery'],
        tablefmt='grid', maxcolwidths=[4, 4])
    widths = [wcswidth(line) for line in report.splitlines()]
    return {'safe_html_escapes_text': '&lt;b&gt;商品&lt;/b&gt;' in escaped and text not in escaped,
        'explicit_unsafe_format_distinct': text in raw,
        'display_width_used': module.WIDE_CHARS_MODE and len(set(widths)) == 1,
        'column_width_not_total_budget': min(widths) > 4}


def cli_observations() -> dict:
    """通过真实候选模块入口读取CSV/JSONL并写文件。@return CLI副作用。"""
    with tempfile.TemporaryDirectory(prefix='tabulate-cli-') as directory:
        output = Path(directory) / 'report.md'
        csv = subprocess.run([sys.executable, '-m', 'tabulate', '--read', 'csv', '-1',
            '--format', 'github', '--output', str(output)], input='name,qty\n"coffee, beans",2\n',
            text=True, capture_output=True, timeout=10)
        jsonl = subprocess.run([sys.executable, '-m', 'tabulate', '--read', 'jsonl', '--format', 'plain'],
            input='{"name":"coffee","qty":2}\n', text=True, capture_output=True, timeout=10)
        bad = subprocess.run([sys.executable, '-m', 'tabulate', '--format', 'no_such_table_format'],
            input='', text=True, capture_output=True, timeout=10)
        written = output.read_text() if output.exists() else ''
        return {'cli_csv_file_output': csv.returncode == 0 and not csv.stdout
                and 'coffee, beans' in written and 'name' in written and 'qty' in written,
            'cli_jsonl_headers': jsonl.returncode == 0 and jsonl.stdout.split() == ['name', 'qty', 'coffee', '2'],
            'cli_invalid_format_rejected': bad.returncode == 3 and 'not a supported output format' in bad.stderr}


def main() -> None:
    """输出冻结任务的真实程序事实。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    selected = {
        'TB-U01': ('numeric_inference_observed',),
        'TB-C01': ('existing_column_policy', 'input_unchanged'),
        'TB-P01': ('existing_column_policy', 'missing_value_policy', 'input_unchanged'),
        'TB-D02': ('tuple_parameters_rejected_original', 'caller_sequences_unchanged'),
        'TB-M01': ('rowalign_tuple_equivalent', 'headerwidth_tuple_equivalent',
            'caller_sequences_unchanged', 'empty_tuple_defaults_preserved', 'ordinary_default_preserved'),
        'TB-U02': ('safe_html_escapes_text', 'explicit_unsafe_format_distinct'),
        'TB-C02': ('display_width_used', 'column_width_not_total_budget'),
        'TB-U03': ('cli_csv_file_output', 'cli_jsonl_headers', 'cli_invalid_format_rejected')}
    if task in ('TB-U01', 'TB-C01', 'TB-P01'):
        facts = numeric_observations()
    elif task in ('TB-D02', 'TB-M01'):
        facts = sequence_observations()
    elif task in ('TB-U02', 'TB-C02'):
        facts = medium_observations()
    else:
        facts = cli_observations()
    print(json.dumps({'candidate_import': Path(module.__file__).resolve() == root / 'library/tabulate/__init__.py',
        **{key: facts[key] for key in selected[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
