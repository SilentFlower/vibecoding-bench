"""制作商品表导入、输出策略和实际字段错位修复任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项业务任务及单一有价值的字典导入修复。@return None。"""
    rows = [
        ('TB-U01', 'understand', '解释CSV表头与文本值', 'Load the literal CSV sku,qty\\nA,2\\nB,\\n with format="csv". Compare default headers with headers=False on sku,qty\\nA,2\\n. Explain value types and missing cells;no edits.',
            'Default headers consume the first row, leaving qty values "2" and "" as strings. headers=False retains ("sku","qty") as the first data row. CSV parsing does not validate numeric quantity or convert blank to None. Define a separate typed schema and missing-value policy.', 'csv_headers_and_cell_values_are_explicit_text_contracts'),
        ('TB-U02', 'understand', '解释导出格式器与原始单元格', 'Create Dataset(("A",2),headers=["sku","qty"]) and add_formatter("qty",lambda value:f"{value:03}"). Compare indexed cells, .dict and CSV export,then indexed cells again. No edits.',
            'Indexed storage remains ("A",2), while .dict projects qty as "002" and CSV exports that formatted text. _package applies callbacks to copied rows, so exporting does not convert stored qty into a string. Keep computation/validation against typed source values and treat formatting callbacks as an output policy.', 'export_formatters_transform_projection_without_changing_stored_cells'),
        ('TB-C01', 'consult', '明确电子表格公式导出策略', 'Create Dataset(("=1+1",),headers=["note"]). Inspect exported XLSX A2 with escape=False/default and escape=True using openpyxl. Advise an explicit formula/text policy for an untrusted report. Do not launch a spreadsheet or implement changes.',
            'Default export writes =1+1 as an XLSX formula cell;the supplied reader only observes its type and does not execute it. escape=True removes the leading equals sign, yielding plain text1+1, so the policy is lossy and leaves source storage unchanged. Choose/validate formula handling for the actual consumer;do not claim universal spreadsheet sanitization or that importing a file executes formulas.', 'xlsx_escape_is_an_explicit_lossy_formula_export_policy'),
        ('TB-P01', 'plan', '规划批量追加的失败发布边界', 'Start Dataset(("A",2),headers=["sku","qty"]). Call extend([("B",3),("C",)]). Inspect final state and plan a robust finite-batch import/retry boundary. No implementation.',
            'extend delegates row by row;the first row is retained before the second raises InvalidDimensions. Final data contains A/2 and B/3. Plan to validate/materialize the finite batch or build a separate Dataset and publish only on complete success. Preserve input identity and conflict/error evidence so retries do not duplicate accepted prefixes;do not claim existing transactional extend.', 'extend_can_keep_a_successful_prefix_after_a_later_invalid_row')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    materials['materials/dict-alignment.md'] = 'A product import assigns Dataset.dict=[{"sku":"A","qty":2},{"qty":5,"sku":"B"}]. The pinned original takes headers from first-row keys but each row values by insertion order,so B is misfiled. Repair only library/src/tablib/core.py and app/test_dict_import.py:align each mapping row by the first-row header names,preserve first-row header order and input mappings. Reject non-dict records,missing keys or extra keys within a mapping batch with existing UnsupportedFormat before replacing existing Dataset state. Retain existing empty-list no-op and positional list-of-lists behavior. JSON and YAML use the same setter and must benefit without format-module edits. Preserve all upstream tests. Deliver meaningful public regression tests that fail on original and pass on the repair;do not change private controls or dependencies.\n'
    definitions.append(('TB-M01', 'modify', '修复商品字典记录的字段错位', 'Implement the supplied bounded mapping-import repair and public regressions. Only the two authorized files may change.', ['materials/dict-alignment.md'], 'repaired_and_regression_verified',
        'Align equal-schema dict rows by header names,not values iteration. Preserve header order and source mappings,including Unicode/None/falsey values;JSON/YAML share the fix. Reject mixed/missing/extra mapping schemas with UnsupportedFormat before replacing existing data. Retain empty-list and positional compatibility. Deliver meaningful public regression tests and preserve every original control.',
        ['mapping_rows_follow_header_names_without_mutating_input', 'json_and_yaml_share_the_repaired_mapping_alignment', 'invalid_mapping_schemas_are_rejected_before_replacing_existing_data', 'empty_list_and_positional_list_compatibility_are_preserved']))
    materials['seed/app/test_dict_import.py'] = '"""请在授权修复中补充商品字典导入的公开回归测试。"""\n'
    definitions.append(('TB-D01', 'diagnose', '诊断首列派生字段的后续错位', 'An inserted computed column is aligned for existing rows but not later appends. Request exact insertion position/callback,headers,input shape and before/after rows. No edits.', [], 'diagnosed_or_information_requested',
        'Use supplied dynamic-column index evidence to locate existing insert/append behavior. Distinguish the requested dict alignment repair from this separate computed-column defect. Missing evidence supports insufficient_information;do not modify another target or fabricate a corrected public API.', None))
    materials['disclosure/dynamic.md'] = 'Start Dataset(("A",2),headers=["sku","qty"]);insert_col(0,lambda row:row[1]*10,header="score");append(("B",3)). Headers are ["score","sku","qty"],old row(20,"A",2),new row("B",3,30). _dynamic_columns is registered at self.width before insertion,not normalized insertion index0. This is a separate source defect;only diagnose,do not extend the mapping-import authorization.\n'
    materials['disclosure/unavailable.md'] = 'Insertion position,callback,headers,input shape and before/after rows are unavailable.\n'
    answers.update({'TB-M01': 'Repaired mapping import in library/src/tablib/core.py to validate the entire dict schema before wiping existing state and then read values by the first-row headers. Added app/test_dict_import.py public regressions for reordered mappings,JSON,YAML,atomic rejection,Unicode/falsey input and existing empty/positional behavior. All upstream controls are preserved.',
        'TB-D01-question': 'Please provide the exact insert_col position/callback,headers,input shape and before/after rows. No edits are authorized for this diagnosis.',
        'TB-D01': 'The supplied rows match a separate dynamic-column index defect. insert_col records the callback at self.width before inserting at0;later append therefore inserts the derived30 at index2,under qty rather than score. A future structural-index repair needs its own scope and regression matrix;the mapping-import repair does not fix or authorize it. Preserve evidence and use a separately validated explicit row construction if needed. No edits were made.',
        'TB-D01-unavailable': 'The insertion/callback,headers,input shape and row controls are unavailable. Record insufficient_information and request them later;an exact cause is unproven. No changes.'})
    build_project('tablib', {'title': 'Tablib商品表工作场景', 'category': '表格导入、导出与字段对齐',
        'description': 'CSV值类型、输出格式器、公式策略、批量失败边界、真实字段错位修复及派生列诊断。'}, definitions,
        [('TB-S01', '数据与展示', '保留类型及输出边界', ['TB-U01', 'TB-U02']),
         ('TB-S02', '报告导出策略', '明确公式处理', ['TB-C01']),
         ('TB-S03', '批量导入方案', '避免部分追加重复', ['TB-P01']),
         ('TB-S04', '商品字段对齐修复', '按真实字段名导入', ['TB-M01']),
         ('TB-S05', '派生列诊断', '明确独立缺陷范围', ['TB-D01'])], materials,
        modifications={'TB-M01': ['library/src/tablib/core.py', 'app/test_dict_import.py']},
        branches={'TB-D01': [{'id': 'dynamic-column-position', 'when': 'Exact insertion/callback,headers,input shape and row controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/dynamic.md']}]},
        extra_entries={'TB-S05': [{'id': 'unavailable', 'task_ids': ['TB-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('tablib-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
