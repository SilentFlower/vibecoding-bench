"""制作Boltons真实重复报告、分批、嵌套记录和JSONL任务。"""
from draft_content import build_project


def main() -> None:
    """生成四场景十项独立数据处理任务。@return None。"""
    materials = {
        'materials/redundancy.py': '''from boltons.iterutils import unique, redundant

values = ["A", "a", "a", "B", "b"]
print(unique(values, key=str.lower))
print(redundant(values, key=str.lower))
print(redundant(values, key=str.lower, groups=True))

class CaseKey:
    """自身真值为False的合法业务归一化函数。"""
    def __call__(self, value):
        """返回业务键。@param value 原值。@return 小写值。"""
        return value.lower()

    def __bool__(self):
        """模拟falsey对象。@return False。"""
        return False

print(redundant(values, key=CaseKey()))
''',
        'materials/key-contract.md': 'Repair redundant so every supported non-None key is used even when a callable has false __bool__ or zero __len__. Preserve the public signature, None identity default, normal callables and attribute-name shorthand, original duplicate values, first-redundancy group order and exception propagation. Support falsey callables that map unhashable business records to hashable keys. Keep both groups=False and groups=True. Do not sort or replace the source values with normalized keys, change other iterator utilities, or alter dependencies/test controls. Only library/boltons/iterutils.py and library/tests/test_iterutils.py may change. Add meaningful original-failing public regressions and preserve all frozen original doctests/main/subtests.\n',
        'materials/batches.py': '''from boltons.iterutils import chunked_iter

def records():
    """产生有限记录并显示实际消费。@return 生成器。"""
    for value in range(5):
        print("consume", value)
        yield value

batches = chunked_iter(records(), 2)
print("created")
print(next(batches))
print(list(batches))
print(list(chunked_iter(range(5), 2, fill=None)))
''',
        'materials/batch-plan.md': 'Process a finite local record source in batches of two, with an explicit final-short-batch policy and failure handling. Explain lazy source consumption, retained per-batch data, any growing deduplication state, and whether already processed batches remain committed or are staged until complete validation. Existing batch helpers are not a transaction or a guarantee that every upstream/downstream component streams. Do not implement changes.\n',
        'materials/nested-record.py': '''from boltons.iterutils import remap, get_path

record = {"line": {"empty": None, "count": 0, "enabled": False, "label": ""}, "notes": [None, "coffee"]}
cleaned = remap(record, visit=lambda path, key, value: value is not None)
print(record)
print(cleaned)
sentinel = object()
print(get_path(record, ("line", "empty"), default=sentinel) is None)
print(get_path(record, ("line", "absent"), default=sentinel) is sentinel)
''',
        'materials/records.jsonl': '{"id":1}\n\nbad\n{"id":2}\n',
        'materials/jsonl-policy.md': 'Read the supplied local JSONL in strict, ignore_errors=True and reverse=True modes. A separate import requirement needs an auditable policy for malformed lines and per-record business schema checks before publication. Decide when skip is acceptable and how to capture line/byte context in application code if required. The pinned JSONLIterator has no on_error callback or schema enforcement; do not invent either or claim that arbitrary JSON values must already be dictionaries. No service is needed.\n'}
    definitions = [
        ('BO-U01', 'understand', '解释唯一项与首个重复项报告',
            'Trace the supplied unique/redundant calls with str.lower. Explain which original values are returned, how groups=True includes the first member, and the actual ordering of redundant groups. Do not edit files.',
            ['materials/redundancy.py'], 'explained',
            'Explain unique retaining A/B, redundant returning the first redundant a/b values and grouped original records ordered by first redundancy. Normalized keys are comparison keys, not substituted return values.', ['ordinary_duplicate_semantics']),
        ('BO-C01', 'consult', '用已有key选择业务重复规则',
            'Recommend an existing API policy for a case-insensitive duplicate report that retains original business values and input order. Compare unique and redundant report needs and state retained-state limits without implementing a library change.',
            ['materials/redundancy.py'], 'advice_no_code_change',
            'Use real key normalization such as str.lower or a suitable business-field callable while retaining original values. Distinguish unique selection from redundancy reporting and do not claim global duplicate detection needs constant memory or returns normalized keys.', ['ordinary_duplicate_semantics']),
        ('BO-D01', 'diagnose', '定位falsey归一化函数被忽略',
            'Use the complete supplied CaseKey reproduction. Explain why a callable accepted by validation still produces a different duplicate report when its own truth value is false. Locate the exact execution boundary and preserve normal callable behavior. Do not edit files.',
            ['materials/redundancy.py'], 'diagnosed',
            'Identify callable validation followed by key_func(i) if key else i, conflating a supported falsey callable with no key. Do not blame str.lower, sorting, business case values or unhashability for the complete supplied string reproduction.', ['original_falsey_key_ignored', 'ordinary_duplicate_semantics']),
        ('BO-M01', 'modify', '修复falsey key并保护分组和错误语义',
            'Implement the complete public falsey-key contract for redundant, including grouped output and zero-length callables over unhashable records. Preserve original values/order, None/default and errors. Modify only the authorized implementation/test files with meaningful original-failing public tests.',
            ['materials/redundancy.py', 'materials/key-contract.md'], 'implemented',
            'Use supported non-None keys independent of object truthiness on both grouping modes. Preserve default/report/error semantics and other utilities; full original main/doctest/subtest regression plus delivered public tests must pass.', ['falsey_callable_respected', 'falsey_group_mode_preserved', 'zero_length_callable_handles_records', 'none_default_preserved', 'invalid_and_key_errors_preserved']),
        ('BO-U02', 'understand', '解释惰性分批和显式尾批填充',
            'Trace the supplied controlled finite source. Explain when chunked_iter consumes records, the first batch, the final short batch and the difference between omitted fill and explicit fill=None. Do not edit files.',
            ['materials/batches.py'], 'explained',
            'Explain creation without source reads, first consumption of two records and final [4] versus [4,None] with explicit fill. Do not equate chunked_iter with eager chunked or treat None as omission of the fill option.', ['chunk_consumption_is_incremental', 'explicit_none_fill_is_distinct']),
        ('BO-P01', 'plan', '规划本地批处理的消费与提交边界',
            'Plan the supplied finite batch-processing workflow with batch size, final-batch policy, validation, source/downstream errors and explicit commit/staging semantics. State memory limits and use current helpers without implementing changes.',
            ['materials/batches.py', 'materials/batch-plan.md'], 'viable_plan_no_library_change',
            'Give a workable current-API plan with positive batch sizes, deliberate short-tail handling and error/commit policy. Separate bounded per-batch storage from growing deduplication state and external side effects; do not claim automatic rollback or end-to-end streaming from one helper.', ['chunk_consumption_is_incremental', 'explicit_none_fill_is_distinct', 'nonpositive_batch_size_rejected']),
        ('BO-U03', 'understand', '解释递归清理时None与其他空值',
            'Trace the supplied remap call. Explain which nested values are removed, what happens to 0/False/empty text and whether the original record is mutated. Describe the visit return shorthand accurately. Do not edit files.',
            ['materials/nested-record.py'], 'explained',
            'Explain value is not None retaining 0, False and empty text while dropping None recursively into a new structure. visit True retains an item and False drops it; do not replace this predicate with generic truthiness or claim source mutation.', ['only_none_removed_recursively']),
        ('BO-C02', 'consult', '用路径默认哨兵区分缺失和None',
            'Recommend an existing get_path policy that distinguishes an existing None value from a missing nested path and reports an actual missing-path error when required. Explain a unique sentinel versus default=None without changing files.',
            ['materials/nested-record.py'], 'advice_no_code_change',
            'Use an explicit unique sentinel for fallback across a failed path, retain actual None values, and explain PathAccessError without a default. Do not invent a schema validator or equate all missing/falsy values.', ['missing_path_distinguished_from_none', 'path_error_remains_explicit']),
        ('BO-U04', 'understand', '核对JSONL坏行与反向读取顺序',
            'Trace the supplied JSONL using the real JSONLIterator in strict, ignore_errors and reverse modes. Explain blank lines, where strict iteration stops and the order of valid values when skipping errors. Do not edit files.',
            ['materials/records.jsonl', 'materials/jsonl-policy.md'], 'explained',
            'Explain first id=1 then a JSON decode error in strict mode, valid ids 1/2 when skipping, and 2/1 in reverse. Blank lines are skipped. Do not claim per-error audit callbacks, business-schema validation or that every JSON value is necessarily an object.', ['strict_jsonl_error_observed', 'skip_and_reverse_order_observed']),
        ('BO-P02', 'plan', '规划可审计的本地JSONL导入',
            'Plan the supplied auditable JSONL import with an explicit malformed-line policy, record schema validation and publication semantics. Choose current iterator convenience or application line-by-line JSON parsing where needed; do not add a library API or implement changes.',
            ['materials/records.jsonl', 'materials/jsonl-policy.md'], 'viable_plan_no_library_change',
            'Use skip only under an accepted policy; when per-line audit is required, track actual positions and parse/validate lines explicitly in application code. Distinguish decode failure, business validation and prior committed effects without inventing an on_error hook or transactions in JSONLIterator.', ['strict_jsonl_error_observed', 'skip_and_reverse_order_observed'])]
    scenes = [('BO-S01', '业务重复项报告与归一化', '解释报告语义并独立修复falsey key', ['BO-U01', 'BO-C01', 'BO-D01', 'BO-M01']),
        ('BO-S02', '有限源的批次消费', '明确惰性、尾批与提交策略', ['BO-U02', 'BO-P01']),
        ('BO-S03', '嵌套记录的清理和访问', '保留实际业务空值并区分路径缺失', ['BO-U03', 'BO-C02']),
        ('BO-S04', '本地JSONL的读取与审计', '按真实错误和顺序选择导入策略', ['BO-U04', 'BO-P02'])]
    build_project('boltons', {'title': 'Boltons批处理与数据清理工作场景', 'category': '记录处理与迭代工具',
        'description': '固定真实源码上的重复报告、falsey key修复、分批、嵌套记录和JSONL导入方案；四场景十任务。'},
        definitions, scenes, materials,
        modifications={'BO-M01': ['library/boltons/iterutils.py', 'library/tests/test_iterutils.py']},
        extra_entries={'BO-S01': [{'id': 'diagnose_only', 'task_ids': ['BO-D01']},
            {'id': 'modify_direct', 'task_ids': ['BO-M01']}]})


if __name__ == '__main__':
    main()
