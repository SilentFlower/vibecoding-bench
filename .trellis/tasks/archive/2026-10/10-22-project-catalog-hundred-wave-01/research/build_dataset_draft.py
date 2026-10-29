"""制作真实Dataset输入、事务、业务键及查询场景，不要求无依据改库。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八个只读任务，所有数据库仅为显式合成SQLite。@return None。"""
    reproduction = '''from pathlib import Path
from tempfile import TemporaryDirectory
import dataset

with TemporaryDirectory() as directory:
    db = dataset.connect("sqlite:///" + str(Path(directory) / "orders.sqlite"))
    try:
        table = db["orders"]
        rows = (dict(order=key) for key in ["A", "B"])
        table.insert_many(rows)
        print(table.count())
    finally:
        db.close()
'''
    materials = {
        'materials/input.json': '[{"order":"A","qty":2},{"order":"B","note":"茶"}]\n',
        'materials/input-rules.md': 'In a new explicit temporary SQLite database, insert_many the supplied dictionary list with chunk_size=1, then find ordered by id. Compare the original caller dictionaries afterward. Next insert {"order":"C","unapproved":"drop-me"} with ensure=False into that existing table. The application wants an explicit error for unapproved fields; assess whether ensure=False already provides that guarantee. Never use environment DATABASE_URL.\n',
        'materials/zero-row-symptom.md': 'An import returned normally but the resulting order table has zero rows. The actual input object type, prior consumption, insert_many call and database lifecycle have not been supplied. Do not assign a cause before obtaining evidence.\n',
        'disclosure/zero-rows.py': reproduction,
        'disclosure/zero-events.md': 'The supplied complete synthetic program prints 0. rows is a fresh one-shot generator, not a list or another reusable Sequence, and it was not consumed before this call. The database is a dedicated temporary SQLite file. No production incident facts beyond this reproduction are available.\n',
        'disclosure/unavailable.md': 'The actual rows type/construction, consumption history, insertion call and database lifecycle cannot be supplied. There is no additional incident reproduction.\n',
        'materials/transactions.md': 'Use a dedicated temporary SQLite database. Before either experiment, create an existing table with order and qty columns by inserting then deleting a seed record. Experiment A raises ValueError after inserting order=outside inside with db, and catches it only outside the context. Experiment B inserts order=inside, raises the same error, catches it inside with db, and then leaves the context normally. Both writes use ensure=False. Compare persisted rows; no schema changes happen during either transaction.\n',
        'materials/import-policy.md': 'A finite order file must be fully accepted or rejected and may exceed memory. The schema and business unique-key policy can be defined before import. Plan explicit input validation, handling of unknown fields, reusable bounded batches, transaction error propagation and retry/recovery. Do not infer cross-database DDL atomicity or atomicity of external side effects from this SQLite example. No changes or real database access are authorized.\n',
        'materials/upsert.md': 'In dedicated temporary SQLite, insert two rows with the same order=A and qty values 1 and 2, with no unique constraint. Call table.upsert({"order":"A","qty":9}, ["order"]). Inspect all matching rows and SQLite PRAGMA index_list for the table. The application also asks whether concurrent workers are guaranteed to create at most one row per order. Do not actually start concurrent database workers.\n',
        'materials/query.md': 'Insert A(score=10,status="x\' OR 1=1 --"), B(score=10,status="ready"), C(score=5,status="ready") in this order into a temporary reports table with the normal id primary key. Query table.find(order_by=["score","id"], _limit=2, _offset=1). Separately call db.query with a named :status bind to select the exact first status literal, ordered by id. Explain ties, ordering and value binding; never build SQL by interpolating the value.\n'}
    definitions = [
        ('DS-U01', 'understand', '解释异构订单字典的列并集和缺失值',
            'Trace the supplied heterogeneous dictionary-list import and ordered rows. Explain column creation, padding of missing values and whether caller dictionaries are mutated. Use actual pinned APIs and do not edit files.',
            ['materials/input.json', 'materials/input-rules.md'], 'explained',
            'insert_many discovers the union of order/qty/note and pads missing per-row values as NULL; ordered rows are A/2/None and B/None/茶. It copies rows rather than mutating original dictionaries. Keep automatically generated id separate from source fields.', ['heterogeneous_columns_union', 'input_dictionaries_unchanged']),
        ('DS-C01', 'consult', '区分关闭自动扩列和拒绝未知字段',
            'Does ensure=False satisfy the supplied requirement to reject unapproved fields? Explain the actual C record result and propose an explicit validation boundary with existing APIs. No library or application files may be changed.',
            ['materials/input.json', 'materials/input-rules.md'], 'advice_with_limits',
            'ensure=False prevents automatic creation and filters unknown fields rather than raising a strict-schema error. Existing order=C is inserted while unapproved is absent. Validate key allowlists and required/types before calling writes; do not claim the ensure flag already rejects unknown fields.', ['ensure_false_filters_unknown_fields']),
        ('DS-D01', 'diagnose', '先取输入对象与消费历史再定位零行导入',
            'Investigate the supplied zero-row symptom. Request actual input type/construction, prior consumption, insert_many call and database lifecycle or an equivalent sufficient reproduction. Diagnose actual disclosed evidence only; unavailable material can legitimately limit the result. Do not edit files.',
            ['materials/zero-row-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient actual input construction/type, consumption history, insertion call and database lifecycle without assuming a cause. Relate disclosed evidence to the real pinned input contract and executed code path, distinguish caller compatibility from a required library change, and state remaining limits. Unavailable evidence permits insufficient_information.', None),
        ('DS-U02', 'understand', '按with边界判断提交与回滚',
            'Compare the two supplied transaction experiments using the existing table. Which row persists, and why does catching the same validation error at a different location change the result? Do not generalize to schema-change atomicity or edit files.',
            ['materials/transactions.md'], 'explained',
            'The escaping error reaches Database.__exit__ and rolls back outside. The error caught inside leaves the context normally, so inside is committed. Explain the error boundary rather than treating the presence of an error log as rollback evidence; all schema is prebuilt.', ['escaping_context_error_rolls_back', 'caught_inside_context_commits']),
        ('DS-P01', 'plan', '规划预校验和完整文件事务导入',
            'Plan the supplied finite-file all-or-nothing import using actual Dataset capabilities. Include unknown-field validation, bounded reusable batches, prebuilt schema, transaction boundaries and error propagation, plus retry limits. No implementation or real database operation is authorized.',
            ['materials/import-policy.md', 'materials/transactions.md', 'materials/input-rules.md'], 'planned_without_library_change',
            'Define schema and identity policy before import, explicitly validate unknown/required fields, prepare reusable bounded batches, and keep all data writes in a real transaction with errors crossing the rollback boundary. Consider large-file transaction/staging costs and restart/idempotency. Do not treat ensure=False, per-chunk auto-commit or SQLite DDL behavior as a general all-or-nothing guarantee.', ['escaping_context_error_rolls_back', 'ensure_false_filters_unknown_fields']),
        ('DS-U03', 'understand', '解释upsert对多个匹配业务键的真实作用',
            'Trace the supplied duplicate-order upsert, including matching row count, quantities and return value. Does this operation merge the existing two rows into one? Do not edit files.',
            ['materials/upsert.md'], 'explained',
            'update matches both rows and changes both qty values to 9; upsert returns True and preserves two rows. It does not collapse duplicate business keys or automatically choose one record. The later insert path only runs when update reports zero matching rows.', ['upsert_updates_all_existing_key_matches']),
        ('DS-C02', 'consult', '明确普通索引和并发唯一性的差别',
            'Assess the concurrent one-row-per-order guarantee requested in the supplied upsert case. Ground the answer in the actual index and update-then-insert implementation. Recommend the required database/application boundary without running concurrency experiments or modifying files.',
            ['materials/upsert.md'], 'advice_with_limits',
            'The automatically created business-key index is ordinary, not a unique constraint. This upsert is update followed by conditional insert, not a single atomic database conflict statement. Define an actual unique constraint and explicit conflict/transaction/retry handling supported by the chosen backend; do not promise concurrency safety from the helper or from a sequential SQLite sample.', ['upsert_updates_all_existing_key_matches', 'automatic_key_index_is_not_unique']),
        ('DS-U04', 'understand', '解释稳定排序、分页和命名参数绑定',
            'Trace the supplied sorted page and named-bound status query. Explain the id tie-breaker and why the quote/comment-like text remains an exact value. Give actual returned order keys and use existing find/query APIs; do not edit files.',
            ['materials/query.md'], 'explained',
            'Ordering by score then id produces C,A,B; offset1/limit2 returns A,B. The named :status parameter binds the entire literal x\' OR 1=1 -- and returns only A, without expanding the WHERE condition. Explicit ordering is required for a specified repeatable page; do not claim default row order or string interpolation is equivalent.', ['explicit_order_limit_offset_are_repeatable', 'named_bind_preserves_literal_value'])]
    scenes = [('DS-S01', '订单输入与列规则', '明确可重用输入、扩列和实际零行取证', ['DS-U01', 'DS-C01', 'DS-D01']),
        ('DS-S02', '有限文件事务导入', '按真实异常边界设计完整导入', ['DS-U02', 'DS-P01']),
        ('DS-S03', '订单业务身份', '区分匹配更新、索引和唯一性保证', ['DS-U03', 'DS-C02']),
        ('DS-S04', '可重复订单查询', '明确排序、分页和字面值绑定', ['DS-U04'])]
    build_project('dataset', {'title': 'Dataset订单数据工作场景', 'category': '本地数据导入与查询',
        'description': '固定真实源码和合成SQLite上的输入契约、列校验、事务、业务键与查询八项独立只读任务。'},
        definitions, scenes, materials,
        branches={'DS-D01': [{'id': 'input-evidence', 'when': 'The actual rows type/construction, consumption history, insertion call and database lifecycle have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests a sufficient reproduction.',
            'materials': ['disclosure/zero-rows.py', 'disclosure/zero-events.md']}]},
        extra_entries={'DS-S01': [{'id': 'diagnose_only', 'task_ids': ['DS-D01']},
            {'id': 'unavailable', 'task_ids': ['DS-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
