"""制作CSVkit投影、筛选取证、类型排序及本地SQL任务。"""
from draft_content import build_project


def main() -> None:
    """保存四场景八项自足只读任务，不把CLI验证重复计为工程任务。@return None。"""
    materials = {
        'materials/orders.csv': 'id,note,amount\n001,"tea, green",2\n002,"line1\nline2",10\n',
        'materials/projection.md': 'Run the existing csvcut tool with -c note,id on the supplied CSV. Preserve identifiers and logical records with quoted commas/newlines. Separately use short.csv with -c b, then -c b -x, then -c a -x. The business must decide whether an empty selected projection is grounds to drop a nonempty original order. No files may be changed.\n',
        'materials/short.csv': 'id,a,b\nA,keep,\nB,,\nC,x\n',
        'materials/filter-symptom.md': 'An operator expected records with a hit in either of two columns, but fewer rows were exported. The exact command, selected columns, pattern mode and input rows have not been provided. Investigate before choosing a cause.\n',
        'disclosure/filter.md': 'Complete synthetic input: id,status,note; rows A,hit,miss / B,miss,hit / C,hit,hit. The command is csvgrep -c status,note -m hit input.csv. Compare the identical input/command with -a appended. No prior cleaning or other flags are present.\n',
        'disclosure/unavailable.md': 'The original command, matching mode and input cannot be supplied. No further evidence is available.\n',
        'materials/matching.md': 'Input sku.csv has one column sku and rows AB,XAB,ABC. Compare csvgrep -c sku -m AB, -f approved.txt containing only AB newline, and -r ^AB$. For a separate complete multi.csv with id,status,note rows A,hit,miss / B,miss,hit / C,hit,hit, compare -c status,note -m hit with and without -a. Decide matches using the actual parser and quoting. No code/data changes are authorized.\n',
        'materials/sort.csv': 'id,amount,note\n001,2,NA\n002,10,keep\n',
        'materials/type-policy.md': 'Use csvsort -c amount -y 0 on sort.csv. Compare default inference, -I --blanks, and --no-leading-zeroes --blanks. Amount must sort numerically while id keeps leading zeros and note NA remains literal text. Explain which flags meet this complete policy and when all-text sorting changes the order. No files may be changed.\n',
        'materials/sales.csv': 'region,amount\neast,2.50\neast,2.50\nwest,1.25\n',
        'materials/sql.md': 'First inspect csvsql -i sqlite -y 0 --tables sales sales.csv without --db, --query or --insert: a reviewer needs schema preview, not a database write. Separately plan/run only a throwaway local report with csvsql -y 0 --tables sales and two --query values: SELECT COUNT(*) AS n FROM sales; then SELECT region, SUM(amount) AS total FROM sales GROUP BY region ORDER BY region. No --db is supplied. Explain connection lifetime, which query result is printed and unchanged input. No external database, production connection string, import/overwrite operation or deployment is authorized.\n'}
    definitions = [
        ('CV-U01', 'understand', '解释CSV投影为何保持引用单元格和编号',
            'Trace the supplied complete csvcut projection and list logical output rows/cells in the selected order. Explain quoted commas/newlines and identifier preservation without naively splitting lines. Do not modify files.',
            ['materials/orders.csv', 'materials/projection.md'], 'explained',
            'Output columns note,id preserve tea, green as one cell, line1 newline line2 as one cell, and exact IDs001/002. There are two data records even though one spans physical lines. csvcut projects CSV strings rather than inferring numeric IDs or splitting raw commas.', ['quoted_projection_preserves_cells_and_identifiers']),
        ('CV-C01', 'consult', '确认删除空行依据的是投影后的字段',
            'Advise on the complete short-row/drop-policy examples using existing csvcut options. Give each actual output and explain whether -x preserves nonempty orders when their selected cells are empty. No code/data changes are requested.',
            ['materials/short.csv', 'materials/projection.md'], 'advice_with_limits',
            'Selecting b produces a header plus three empty cells, including padding for short rowC. Adding -x leaves only the b header; selecting a with -x keeps keep and x. The empty check occurs after projection, so original nonempty IDs do not prevent dropping. Choose an explicit business filter rather than treating -x as validation of complete original rows.', ['delete_empty_rows_uses_projected_cells_and_pads_short_rows']),
        ('CV-D01', 'diagnose', '先取实际筛选命令再定位漏选记录',
            'Investigate the supplied fewer-exported-rows symptom. Request the actual command/options, selected columns, matching mode and representative input before choosing a cause. Diagnose disclosed facts only; close with an evidence plan if unavailable. Do not change files.',
            ['materials/filter-symptom.md'], 'diagnosed_no_code_change',
            'The initial expectation cannot establish actual multi-column combination or pattern semantics. Request sufficient exact command and rows, then explain only the disclosed result and compatible existing option. insufficient_information is valid when missing. Do not assume hidden -a absence, malformed quoting or a library defect before disclosure.', None),
        ('CV-U02', 'understand', '区分子串、精确名单和多列匹配组合',
            'Trace all complete matching controls in the supplied material. Give exact selected rows for substring/file/anchored-regex and default multi-column/all versus explicit any matching. No changes are authorized.',
            ['materials/matching.md'], 'explained',
            '-m AB is substring and keepsAB/XAB/ABC; the file containingAB and anchored ^AB$ each keep onlyAB. Multiple selected columns default to all matching, keepingC; -a changes to any, keepingA/B/C. Match mode and combination mode are distinct settings; neither is SQL equality inferred from a string argument.', ['match_is_substring_while_file_and_anchored_regex_are_exact', 'multiple_columns_default_to_all_and_any_is_explicit']),
        ('CV-U03', 'understand', '解释数值排序与全字符串模式的不同顺序',
            'Trace actual amount order under default inference and -I for the complete sort reproduction. Explain the role of -y 0 and distinguish input parsing from row sorting. Do not modify files.',
            ['materials/sort.csv', 'materials/type-policy.md'], 'explained',
            'Default numeric amount order is2 then10; -I makes amounts text and orders10 before2. -y0 disables delimiter sniffing, not type inference. All-text mode is not a lossless way to keep numeric ordering automatically.', ['numeric_and_no_inference_sort_have_different_order']),
        ('CV-C02', 'consult', '兼顾数值排序、前导零编号和字面NA',
            'Meet the supplied complete typing/sorting policy with existing options. Compare all-text mode with targeted leading-zero and null-token policies, including exact controls and input ownership. No implementation is requested.',
            ['materials/sort.csv', 'materials/type-policy.md'], 'advice_no_code_change',
            '--no-leading-zeroes --blanks with inference retains IDs001/002 and literalNA while amounts2/10 stay numeric and sort numerically. Default inference emits ID1 and blank forNA. -I --blanks retains text but sorts10 before2, so it misses the numeric-order requirement. Source input is not rewritten.', ['leading_zero_and_blank_policies_preserve_business_text']),
        ('CV-C03', 'consult', '确认DDL预览和实际数据库导入的区别',
            'Explain the complete schema-preview invocation and recommend how the reviewer can inspect it without database writes. Identify what the command actually emits and avoid executing unrequested import/overwrite flags.',
            ['materials/sales.csv', 'materials/sql.md'], 'advice_no_code_change',
            'The dialect-only invocation with no --db/query/insert emits a CREATE TABLE sales statement, not INSERT statements or a persisted database import. Inspect it as a preview; inferred schema is not a guarantee about future data. Do not add --db, --insert or --overwrite when only a preview is authorized.', ['dialect_only_outputs_schema_without_importing_data']),
        ('CV-P01', 'plan', '规划仅在内存中汇总CSV的本地报表',
            'Plan the complete local-only reporting invocation with current CSVSQL behavior. State the implied connection, input lifetime, actual last-query output and controls; no external database access or implementation is authorized.',
            ['materials/sales.csv', 'materials/sql.md'], 'planned_without_library_change',
            'With --query and no --db the utility creates SQLite memory storage, imports the synthetic CSV into its scoped transaction, runs both queries and prints only the final result: region,total with east5 and west1.25. The earlier count result is not also printed; the connection is closed and input remains unchanged. Keep exact trusted SQL/table ownership and use local controls, not production connection strings or an assumed persisted artifact.', ['query_without_database_uses_memory_and_outputs_last_result'])]
    scenes = [('CV-S01', 'CSV投影与空行政策', '按逻辑单元格保真并明确丢弃规则', ['CV-U01', 'CV-C01']),
        ('CV-S02', '筛选取证与匹配方式', '分清实际命令、匹配模式和多列组合', ['CV-D01', 'CV-U02']),
        ('CV-S03', '金额排序与字段保真', '兼顾数值顺序、外部编号和字面空值标记', ['CV-U03', 'CV-C02']),
        ('CV-S04', 'SQL预览与本地汇总', '明确DDL输出、内存查询和连接生命周期', ['CV-C03', 'CV-P01'])]
    build_project('csvkit', {'title': 'CSVkit数据导出工作场景', 'category': 'CSV命令行与本地查询',
        'description': '固定真实源码上的引用投影、筛选取证、类型排序、字段保真、DDL预览和内存汇总八项独立只读任务。'},
        definitions, scenes, materials,
        branches={'CV-D01': [{'id': 'filter-evidence', 'when': 'The exact command/options, matching mode and input rows have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/filter.md']}]},
        extra_entries={'CV-S02': [{'id': 'diagnose_only', 'task_ids': ['CV-D01']},
            {'id': 'unavailable', 'task_ids': ['CV-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
