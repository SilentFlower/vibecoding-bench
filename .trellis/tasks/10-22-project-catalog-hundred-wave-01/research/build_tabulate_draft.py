"""制作逐仓研究确定的Tabulate报表任务，不生成同构业务问题。"""
from draft_content import build_project


def main() -> None:
    """生成五场景九任务的独立草稿。@return None。"""
    materials = {
        'materials/products.json': '[["00123", "2.50"], ["1e3", "3.00"]]\n',
        'materials/numeric-report.py': '''from tabulate import tabulate

rows = [["00123", "2.50"], ["1e3", "3.00"]]
print(tabulate(rows, headers=["sku", "price"], tablefmt="plain"))
''',
        'materials/report-requirements.md': 'Produce a readable inventory report with explicit SKU/price columns, literal SKU identifiers, two decimal places for prices and N/A for None. Preserve the source records. Keep machine-readable CSV/JSON exports separate from display tables; choose an explicit policy for missing versus empty text. Do not implement a library change.\n',
        'materials/display-symptom.md': 'A report no longer displays some product identifiers exactly as stored. The original values, tabulate call and output are not available yet. Do not assume coercion, corruption or a formatting defect from this symptom alone.\n',
        'disclosure/actual-report.py': '''from tabulate import tabulate

rows = [["00123", "2.50"], ["1e3", "3.00"]]
print(tabulate(rows, headers=["sku", "price"], tablefmt="plain"))
''',
        'disclosure/actual-output.txt': '  sku    price\n  123      2.5\n 1000      3\n',
        'disclosure/unavailable.md': 'The original values, exact call and actual output cannot be provided. No further incident evidence is available.\n',
        'materials/tuple-layout.py': '''from tabulate import tabulate

rows = [["coffee\\nbeans", "ready"], ["tea", "packed"]]
headers = ["Product name", "Shipping note"]
print(tabulate(rows, headers=headers, tablefmt="grid", rowalign=["bottom"]))
print(tabulate(rows, headers=headers, tablefmt="grid", rowalign=("bottom",)))
print(tabulate(rows, headers=headers, tablefmt="grid", maxheadercolwidths=(6,)))
''',
        'materials/tuple-contract.md': 'Repair tuple sequence handling in the existing argument-expansion path so rowalign and maxheadercolwidths tuples produce exactly the same output as equal lists. Preserve empty tuples, short-sequence defaults, existing longer-sequence behavior, scalar defaults and original list output. Do not mutate caller sequences. Keep the public signature and dependencies, and do not add unsized iterator support or change numeric/formatting policy. Only library/tabulate/__init__.py and library/test/test_api.py may change. Add meaningful public tests that fail on the original and pass after the repair; preserve original doctests and all pytest controls.\n',
        'materials/output-medium.py': '''from tabulate import tabulate

print(tabulate([["<b>商品</b>"]], tablefmt="html"))
print(tabulate([["<b>商品</b>"]], tablefmt="unsafehtml"))
print(tabulate([["咖啡咖啡咖啡", "长期订阅订单"]], headers=["Product", "Delivery"], tablefmt="grid", maxcolwidths=[4, 4]))
''',
        'materials/cli-inputs.md': '''The candidate includes tabulate/__main__.py and tabulate/cli.py.
CSV stdin: name,qty followed by a row with the quoted first field "coffee, beans" and qty 2.
Use --read csv -1 --format github --output <local-file>.
JSONL stdin: {"name":"coffee","qty":2}. Use --read jsonl --format plain.
Also inspect --format no_such_table_format. No network or external service is required.
'''}
    definitions = [
        ('TB-U01', 'understand', '解释数字形商品标识符与金额显示',
            'Trace the supplied report. Explain the displayed SKU and price values, column type inference and default numeric formatting. Distinguish changed display from mutated source records. Do not edit files.',
            ['materials/products.json', 'materials/numeric-report.py'], 'explained',
            'Explain mixed numeric-looking SKU column inference, 00123/1e3 display as 123/1000 and default g price formatting; do not claim source records were rewritten.', ['numeric_inference_observed']),
        ('TB-C01', 'consult', '用已有按列策略保护商品标识符',
            'Recommend an existing API call that preserves the literal SKU strings while displaying prices with two decimal places. Explain global versus per-column disable_numparse and decide whether the library needs a patch. Do not edit files.',
            ['materials/products.json', 'materials/numeric-report.py'], 'advice_no_code_change',
            'Use the real per-column disable_numparse=[0] with floatfmt=.2f or a correct equivalent, preserving SKU text and numeric price formatting without requiring a library repair.', ['existing_column_policy', 'input_unchanged']),
        ('TB-P01', 'plan', '规划库存报表与机器导出边界',
            'Plan the supplied inventory report: explicit field order, literal identifiers, prices, None versus empty strings, immutable source records and a separate machine-readable export. Use existing APIs and state format limits. Do not implement changes.',
            ['materials/products.json', 'materials/report-requirements.md'], 'viable_plan_no_library_change',
            'Provide a feasible existing-API display policy and separate CSV/JSON serialization. Explain missingval for None and numeric formatting without treating an aligned display table as lossless machine interchange.', ['existing_column_policy', 'missing_value_policy', 'input_unchanged']),
        ('TB-D01', 'diagnose', '先取原值和调用再判断标识符变化',
            'Investigate the supplied display symptom. Request original values, the exact formatting call and observed output before assigning a cause. Use actual subsequent evidence; if unavailable, state the limit and evidence plan. Do not edit files.',
            ['materials/display-symptom.md'], 'diagnosed_no_code_change',
            'The initial symptom alone is insufficient. Request the actual values/call/output or an equivalent reproduction. Diagnose only disclosed evidence; accept insufficient_information when those materials cannot be provided, without inventing values or a cause.', None),
        ('TB-D02', 'diagnose', '定位tuple排版参数与list的差异',
            'Trace the complete supplied layout reproduction. Explain why list configuration works while rowalign and maxheadercolwidths tuples fail. Locate the shared source boundary and preserve the successful controls. Do not edit files.',
            ['materials/tuple-layout.py'], 'diagnosed',
            'Locate the existing _expand_iterable sequence plus list padding operation and its tuple TypeError. Explain both affected paths rather than blaming the table data or a nonexistent public parameter.', ['tuple_parameters_rejected_original', 'caller_sequences_unchanged']),
        ('TB-M01', 'modify', '统一tuple排版序列并保持原有输出',
            'Repair the complete supplied tuple/list layout contract. Cover rowalign and maxheadercolwidths, preserve defaults and caller sequences, and deliver meaningful original-failing public tests. Modify only the two authorized files.',
            ['materials/tuple-layout.py', 'materials/tuple-contract.md'], 'implemented',
            'Satisfy tuple/list equivalence on both public argument paths without mutating inputs or changing signatures, dependencies, default output, numeric policy, doctests or test controls. The independent matrix and complete frozen original suite must pass.', ['rowalign_tuple_equivalent', 'headerwidth_tuple_equivalent', 'caller_sequences_unchanged', 'empty_tuple_defaults_preserved', 'ordinary_default_preserved']),
        ('TB-U02', 'understand', '解释HTML文字转义与显式原始标记',
            'Explain the two HTML outputs for the supplied ordinary <b>商品</b> cell. Which output treats it as literal text and which preserves markup? Distinguish explicit format selection from a general guarantee about every output medium. Do not edit files.',
            ['materials/output-medium.py'], 'explained',
            'Explain safe html escaping and explicit unsafehtml raw markup using actual output. Do not equate their behavior or claim Markdown/terminal output inherits HTML escaping.', ['safe_html_escapes_text', 'explicit_unsafe_format_distinct']),
        ('TB-C02', 'consult', '规划中文终端表的显示宽度',
            'Assess the supplied Chinese grid output under the pinned wcwidth environment. Explain display columns versus Python character counts, maxcolwidths versus a whole-table terminal budget, and existing configuration/application choices. Do not promise an automatic total-width allocator or modify files.',
            ['materials/output-medium.py'], 'advice_with_limits',
            'Use actual wcwidth-enabled display width and per-column wrapping behavior. Account for headers, separators and padding when discussing a total budget; do not invent a max_table_width API or claim a column cap is a whole-table cap.', ['display_width_used', 'column_width_not_total_budget']),
        ('TB-U03', 'understand', '核对真实CLI的CSV与JSONL输入输出',
            'Explain and, where useful, run the supplied candidate CLI cases. Cover quoted CSV commas, first-row headers, JSONL keys, file versus stdout output and unsupported output format status. Distinguish actual CLI options from richer Python API options. Do not edit files.',
            ['materials/cli-inputs.md'], 'explained',
            'Use the real candidate module CLI, preserve the quoted CSV field as one cell, explain default JSONL key headers and local file output, and identify exit code 3 for unsupported format. Do not invent CLI flags from Python API parameter names.', ['cli_csv_file_output', 'cli_jsonl_headers', 'cli_invalid_format_rejected'])]
    scenes = [('TB-S01', '商品标识符与库存报表', '用已有格式策略表达真实业务数据', ['TB-U01', 'TB-C01', 'TB-P01']),
        ('TB-S02', '标识符变化的最小取证', '先取得实际数据再诊断显示变化', ['TB-D01']),
        ('TB-S03', '可复用的序列排版配置', '独立诊断并修复tuple与list不一致', ['TB-D02', 'TB-M01']),
        ('TB-S04', 'HTML与中文终端输出', '按介质选择文字表示与宽度策略', ['TB-U02', 'TB-C02']),
        ('TB-S05', '本地报表CLI', '核真实输入格式、表头与文件副作用', ['TB-U03'])]
    build_project('tabulate', {'title': 'Tabulate业务报表工作场景', 'category': '报表表示与终端输出',
        'description': '固定真实源码上的商品报表、数据取证、tuple修复、HTML、中文宽度和本地CLI；五场景九任务。'},
        definitions, scenes, materials,
        modifications={'TB-M01': ['library/tabulate/__init__.py', 'library/test/test_api.py']},
        branches={'TB-D01': [{'id': 'report-evidence', 'when': 'The actual source values, formatting call and output have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests them or an equivalent sufficient reproduction.',
            'materials': ['disclosure/actual-report.py', 'disclosure/actual-output.txt']}]},
        extra_entries={'TB-S02': [{'id': 'diagnose_only', 'task_ids': ['TB-D01']},
            {'id': 'unavailable', 'task_ids': ['TB-D01'], 'materials': ['disclosure/unavailable.md']}],
            'TB-S03': [{'id': 'diagnose_only', 'task_ids': ['TB-D02']}, {'id': 'modify_direct', 'task_ids': ['TB-M01']}]})


if __name__ == '__main__':
    main()
