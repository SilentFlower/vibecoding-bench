"""制作CLI Helpers独立导出任务，格式语义与状态隔离分别验收。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项真实导出任务。@return None。"""
    materials = {
        'materials/export-formats.py': '''from cli_helpers.tabular_output import format_output

rows = [["coffee, beans", None], ["咖啡", 2]]
headers = ["product", "quantity"]
for name in ("simple", "csv", "jsonl"):
    print(name)
    print("\\n".join(format_output(rows, headers, format_name=name)))
''',
        'materials/export-contract.md': 'A local query report serves a terminal user and a separate machine importer. Define explicit ordered field names, null versus empty text, Unicode, comma quoting, types and output consumption. Keep readable display and machine exchange separate. Explain whether the current formatter materializes rows and when partial file output can occur; choose validation/staging policy instead of promising constant memory or transactions. Do not modify files.\n',
        'materials/json-boundaries.py': '''from decimal import Decimal
from cli_helpers.tabular_output import format_output

print(list(format_output([[1, 2]], ["id", "id"], format_name="jsonl")))
value = Decimal("0.12345678901234567890123456789")
print(list(format_output([[value]], ["price"], format_name="jsonl")))
''',
        'materials/strict-json-requirements.md': 'The importer requires distinct column keys and exact decimal text. Existing default JSONL output is not asserted to provide either a duplicate-header error policy or Decimal text mode. Recommend an application pre-validation/pre-formatting policy using existing capabilities without modifying the library; make any resulting JSON string-versus-number type explicit.\n',
        'materials/option-leak.py': '''from cli_helpers.tabular_output import TabularOutputFormatter

first = TabularOutputFormatter("simple")
print("\\n".join(first.format_output([[None]], ["value"], missing_value="N/A")))
second = TabularOutputFormatter("simple")
print("\\n".join(second.format_output([[None]], ["value"])))
''',
        'materials/option-contract.md': 'Repair per-call top-level option isolation in TabularOutputFormatter.format_output. Registered formatter defaults and the registration caller default dictionary must not be changed by call kwargs. Current overrides still win for that call; repeated calls, different instances, deferred output consumption, built-in formats and custom registered handlers must remain independent. Preserve signatures, preprocessors, iterator results and dependencies. This is not recursive cloning of arbitrary nested style objects or control of a third-party handler mutating its own nested objects. Only library/cli_helpers/tabular_output/output_formatter.py and library/tests/tabular_output/test_output_formatter.py may change. Add meaningful original-failing public tests and preserve the complete original suite and controls. Do not bundle color-state, Decimal-policy or row-iterator repairs.\n',
        'materials/one-shot-rows.py': '''from cli_helpers.tabular_output import format_output

values = [["coffee", 2], ["tea", 3]]
rows = (iter(row) for row in values)
print(list(format_output(rows, ["product", "quantity"], format_name="csv")))
'''}
    definitions = [
        ('CH-U01', 'understand', '解释显示表、CSV和JSONL的真实数据表示',
            'Trace the supplied three-format export. Explain how the output is consumed and how commas, Unicode and None appear in a readable table, CSV and JSONL. Distinguish representation from mutated source data. Do not edit files.',
            ['materials/export-formats.py'], 'explained',
            'Explain actual iterator consumption, CSV quoting/empty missing field, JSONL Unicode and null, and the display <null> marker. Do not equate all output formats or claim the input records are modified.', ['csv_quotes_and_missing', 'jsonl_retains_unicode_and_null', 'display_missing_marker']),
        ('CH-C01', 'consult', '选择人读报表和机器交换格式',
            'Recommend existing formatter choices for the supplied terminal report and machine importer. Explain how to consume results, preserve quoted commas/Unicode and handle nulls, without treating a padded display table as lossless serialization or changing the library.',
            ['materials/export-formats.py', 'materials/export-contract.md'], 'advice_no_code_change',
            'Choose existing CSV/JSONL for defined machine exchange and a display format for people. Explain the actual None policies and iterator interface with correct consumption; no library modification is required for selecting formats.', ['csv_quotes_and_missing', 'jsonl_retains_unicode_and_null']),
        ('CH-P01', 'plan', '规划明确列和失败边界的数据导出',
            'Plan the supplied local export contract with ordered fields, null/type rules, Unicode, output consumption, validation and file publication. State memory and partial-output limits from the real pipeline. Do not implement changes.',
            ['materials/export-formats.py', 'materials/export-contract.md'], 'viable_plan_no_library_change',
            'Give a feasible application export plan, explicit serializer/field/null policy and deliberate staging or partial-output handling. Current format_output may materialize rows; do not promise constant-memory streaming, automatic validation of every business schema or transactions.', ['csv_quotes_and_missing', 'jsonl_retains_unicode_and_null', 'source_records_unchanged']),
        ('CH-D01', 'diagnose', '定位JSONL同名列与Decimal精度边界',
            'Use the complete supplied JSONL reproduction. Explain why one duplicate id value disappears and the Decimal does not retain all digits. Locate the actual adapter operations and distinguish observed representation limits from an already supported strict export mode. Do not edit files.',
            ['materials/json-boundaries.py'], 'diagnosed',
            'Identify dict(zip(headers,row,strict=True)) overwriting equal keys and CustomEncoder converting Decimal to float. strict zip checks lengths, not unique keys. Do not invent an existing duplicate_headers or decimal_mode option.', ['duplicate_header_last_value', 'decimal_numeric_output_not_exact']),
        ('CH-C02', 'consult', '用应用校验和显式字符串满足严格JSON需求',
            'Meet the supplied strict JSON importer requirements using existing application preprocessing where possible. Explain unique-header validation, Decimal text preservation and the resulting JSON type, without modifying files or silently changing every existing caller.',
            ['materials/json-boundaries.py', 'materials/strict-json-requirements.md'], 'advice_no_code_change',
            'Validate header uniqueness before export and explicitly pre-format Decimal as text when exact decimal text is required, preserving it as a JSON string. Do not claim numeric Decimal output is lossless or invent a built-in strict mode; an application policy avoids a required library modification.', ['application_unique_header_check', 'existing_string_preformat_preserves_decimal']),
        ('CH-D02', 'diagnose', '定位跨实例缺值选项污染',
            'Trace the complete missing-value reproduction. Explain why a later new formatter instance inherits a prior per-call option. Locate the shared mutation and distinguish it from input mutation or a chosen per-instance default. Do not edit files.',
            ['materials/option-leak.py'], 'diagnosed',
            'Locate the class-level registered formatter_args dictionary and in-place update in format_output. A new formatter object still reaches the shared mutated defaults; changing the source row or constructing another instance does not fix that boundary.', ['original_default_leak_observed']),
        ('CH-M01', 'modify', '隔离每次格式覆盖并保持注册默认',
            'Repair the complete per-call top-level option isolation contract for built-in and custom formatters. Preserve override priority, defaults, callers, preprocessors and output consumption. Modify only the authorized files and add meaningful original-failing public tests.',
            ['materials/option-leak.py', 'materials/option-contract.md'], 'implemented',
            'Ensure per-call kwargs do not mutate registered or registration-caller defaults across instances or repeated/deferred consumption, including custom handlers. Preserve signatures and pipeline behavior, and do not broaden the patch to unrelated formatting issues. Complete original regression and public tests must pass.', ['builtin_defaults_isolated', 'custom_defaults_isolated', 'caller_default_mapping_unchanged']),
        ('CH-C03', 'consult', '处理一次性行输入的有界兼容需求',
            'Explain the supplied generator-of-row-iterators result and recommend a compatible application workaround for a known finite local result set. Locate the repeated-consumption boundary, bound memory explicitly, and state limits for unbounded input. Do not edit files or claim a library repair has been delivered.',
            ['materials/one-shot-rows.py'], 'advice_with_limits',
            'Explain outer list materialization without stabilizing each row, followed by type scanning consuming row iterators. Materialize each row for the finite input or use a correctly bounded compatible boundary. Do not promise end-to-end constant memory, support for infinite data, or a delivered library fix.', ['one_shot_rows_are_consumed', 'bounded_row_materialization_works'])]
    scenes = [('CH-S01', '查询结果的显示与机器导出', '选择真实格式并规划明确导出合同', ['CH-U01', 'CH-C01', 'CH-P01']),
        ('CH-S02', 'JSON字段与精度边界', '诊断表示限制并给出兼容策略', ['CH-D01', 'CH-C02']),
        ('CH-S03', '每次输出的选项隔离', '独立定位并修复共享默认污染', ['CH-D02', 'CH-M01']),
        ('CH-S04', '一次性行结果的消费', '为有限输入选择兼容且有界的办法', ['CH-C03'])]
    build_project('cli-helpers', {'title': 'CLI Helpers数据输出工作场景', 'category': '查询导出与格式管线',
        'description': '固定真实源码上的CSV/JSONL、数据保真、导出方案、选项隔离修复和一次性行输入咨询；四场景八任务。'},
        definitions, scenes, materials,
        modifications={'CH-M01': ['library/cli_helpers/tabular_output/output_formatter.py', 'library/tests/tabular_output/test_output_formatter.py']},
        extra_entries={'CH-S03': [{'id': 'diagnose_only', 'task_ids': ['CH-D02']},
            {'id': 'modify_direct', 'task_ids': ['CH-M01']}]})


if __name__ == '__main__':
    main()
