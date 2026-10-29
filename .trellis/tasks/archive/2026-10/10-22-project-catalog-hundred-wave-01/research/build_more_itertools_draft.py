"""制作流式预览、严格分批、订单去重和有界回看的独立业务任务。"""
from draft_content import build_project


def main() -> None:
    """生成无需改库的四场景九任务，不把既有迭代器行为当缺陷。@return None。"""
    reproduction = '''from more_itertools import chunked
committed = []
try:
    for batch in chunked(iter(range(5)), 2, strict=True):
        committed.extend(batch)
except ValueError as error:
    print(type(error).__name__)
print(committed)
'''
    materials = {
        'materials/preview.md': 'A single-use source yields 0..4 and records every value pulled. Run head, replay = spy(source, 2), inspect the pulls immediately, then consume replay. Separately wrap a source yielding A,B,C in peekable, call bool(wrapper), peek(), wrapper[-1], and finally list(wrapper). Report when the original sources advance, whether the returned stream loses or repeats records, and cache/memory limits.\n',
        'materials/batches.md': 'A synthetic finite order stream yields 0..4. Compare chunked(source, 2) with strict=True. For the strict version, append each yielded batch to a local committed list before requesting the next batch; record every input pull. This list represents already completed external work only for this synthetic example.\n',
        'materials/partial-symptom.md': 'A batch import ended with an error, but some orders were already visible. The source iterator, chunk size/strict setting, loop, side-effect ordering and transaction boundaries have not been supplied. Investigate before deciding the cause.\n',
        'disclosure/partial.py': reproduction,
        'disclosure/partial-events.md': 'This is the complete synthetic reproduction. It prints ValueError followed by [0, 1, 2, 3]. Each list append completes before requesting the next batch; no transaction or undo operation is present. No production database or account is involved.\n',
        'disclosure/unavailable.md': 'The source construction, chunk options, processing loop and transaction/commit ordering cannot be provided. There is no further incident reproduction.\n',
        'materials/atomic-import.md': 'A finite input file must be fully accepted or rejected; its size can exceed memory. Existing input iteration, validation and external storage writes are separate operations. Plan with current library capabilities and state how temporary staging, real storage transactions, validation errors, retry/idempotency and upstream re-readability affect the guarantee. No files may be changed and no storage service is provided.\n',
        'materials/orders.json': '[{"order":"A","rev":1},{"order":"A","rev":2},{"order":"B","rev":1},{"order":"A","rev":3}]\n',
        'materials/dedup-requirements.md': 'For order events, retain the first event per exact order key and preserve arrival order; do not select the latest revision. Separately deduplicate label lists [["tea","new"],["tea","new"],["new","tea"]] with ordered label equality. Compare raw unique_everseen with an explicit tuple key. For audit, distinguish every later duplicate event from one representative per duplicated order.\n',
        'materials/seek.md': 'Use seekable("ABCD", maxlen=2), retain view = stream.elements(), consume A,B,C, inspect view, seek(0), consume three more items, inspect the original view again. Separately use seekable("AB", maxlen=0), peek(), next(), and inspect elements(). The consumer also asks whether this in-memory object alone can resume after process restart.\n'}
    definitions = [
        ('MI-U01', 'understand', '解释取样对单次源和回放流的不同影响',
            'Trace the supplied spy experiment, including source pulls before and after consuming the returned replay iterator. Explain why reading the original source directly afterward differs from using replay. Do not edit files.',
            ['materials/preview.md'], 'explained',
            'spy has already pulled 0 and 1 to create head; replay still yields 0..4 exactly once, and original source pulls total 0..4 once. Continue with the returned iterator, not the advanced original. Do not claim zero source consumption.', ['spy_preserves_returned_stream', 'spy_advances_source_once']),
        ('MI-C01', 'consult', '为有限前瞻选择缓存方式',
            'Advise whether the supplied peekable access pattern is suitable for a potentially unbounded stream. Explain bool, peek, negative indexing and retained output using the actual finite reproduction. No code changes are authorized.',
            ['materials/preview.md'], 'advice_with_limits',
            'bool and peek may pull and cache the first source item without removing it from the wrapper; index -1 consumes and caches the remaining finite source. Avoid negative indexing on an unbounded stream and choose an explicit bounded lookahead/cache policy.', ['peek_and_bool_cache_one', 'negative_index_consumes_remainder']),
        ('MI-U02', 'understand', '定位严格分批的延迟异常和末尾消费',
            'Trace normal and strict chunking of the supplied five records. Identify complete batches emitted, the incomplete tail consumed, and the point ValueError is raised. Does strict=True prevalidate the entire input before yielding anything? Do not edit files.',
            ['materials/batches.md'], 'explained',
            'Normal chunking yields [0,1],[2,3],[4]. Strict chunking yields the first two batches then consumes 4 and raises before yielding that final partial batch. The strict flag is not a whole-stream preflight or rollback guarantee.', ['strict_yields_complete_batches_before_error', 'strict_consumes_incomplete_tail', 'default_keeps_partial_batch']),
        ('MI-D01', 'diagnose', '先取实际导入与提交时序再判断部分完成',
            'Investigate the supplied partial-import symptom. Request the actual iterator/options, loop and side-effect or commit boundaries before attributing the incident. Diagnose disclosed evidence only; close with an evidence plan if it cannot be provided. Do not edit files.',
            ['materials/partial-symptom.md'], 'diagnosed_no_code_change',
            'The initial symptom is insufficient. Request a sufficient actual loop/options and side-effect/transaction reproduction. Relate only disclosed input, processing and commit evidence to actual pinned APIs, state the supported conclusion and remaining limits, and do not assign a cause before disclosure. If unavailable, insufficient_information is legitimate.', None),
        ('MI-P01', 'plan', '规划有限文件的完整校验与原子导入',
            'Plan the supplied all-or-nothing finite-file import with existing iterator helpers and application/storage controls. Address files larger than RAM, validation, transaction or staging boundaries, retries and irreversible external writes. Do not implement or invent a library transaction API.',
            ['materials/atomic-import.md', 'materials/batches.md'], 'planned_without_library_change',
            'Separate iterator batch validation from side-effect atomicity. Offer a bounded-memory staged/validated input or re-readable preflight plus a real storage transaction or explicit publish boundary. Explain limits for irreversible external writes and define recovery/idempotency; strict chunking alone cannot ensure all-or-nothing.', ['strict_yields_complete_batches_before_error', 'earlier_side_effects_not_rolled_back']),
        ('MI-C02', 'consult', '用显式键满足订单首条与标签次序去重',
            'Meet the supplied first-order-event and ordered-label dedup requirements with existing APIs. Explain output order, raw unhashable label behavior and an explicit key. Do not substitute latest-revision selection or modify the library.',
            ['materials/orders.json', 'materials/dedup-requirements.md'], 'advice_no_code_change',
            'Use unique_everseen with order key to retain A/rev1 then B/rev1. In this pinned version raw unhashable lists raise TypeError; key=tuple supports ordered list equality and retains [tea,new] separately from [new,tea]. Do not claim automatic latest selection or hashability of dict events.', ['key_keeps_first_event_in_order', 'explicit_key_handles_unhashable_labels']),
        ('MI-U03', 'understand', '区分逐次重复事件和重复订单代表',
            'For the supplied event sequence, explain duplicates_everseen keyed by order. List which original event records appear and how to obtain one representative per duplicated order with current helpers. Do not edit files.',
            ['materials/orders.json', 'materials/dedup-requirements.md'], 'explained',
            'The later A/rev2 and A/rev3 events both appear; original A/rev1 and unique B/rev1 do not. Compose unique_everseen on that output with the same key to obtain A/rev2 once. Preserve original record identity and arrival order.', ['duplicates_keep_every_later_event', 'one_duplicate_per_key_requires_composition']),
        ('MI-U04', 'understand', '解释有限缓存的相对起点和动态视图',
            'Trace the supplied maxlen=2 seekable experiment. Explain what seek(0) means after cache eviction, what the retained SequenceView shows before and after reading D, and whether original A is still replayable from this object. Do not edit files.',
            ['materials/seek.md'], 'explained',
            'After consuming ABC the cache is BC; seek(0) starts at current cache B and the next three reads are B,C,D. The retained view changes to CD. Evicted A is not restored by an index of zero.', ['bounded_seek_zero_uses_current_cache', 'sequence_view_tracks_cache_eviction']),
        ('MI-C03', 'consult', '区分内存回看与进程重启检查点',
            'Advise on bounded lookahead and process-restart recovery for the supplied seekable consumer. Explain maxlen=0 peek behavior and identify what durable position/source guarantees must come from the application or upstream. No files may be changed.',
            ['materials/seek.md'], 'advice_with_limits',
            'With maxlen=0, peek still preserves the next item while elements stays empty. seekable is an in-memory cache, not a durable checkpoint or upstream rewind. Define source identity/offset, re-readability and completed-side-effect checkpointing for restart; do not promise replay of evicted data.', ['bounded_seek_zero_uses_current_cache', 'zero_cache_peek_preserves_next'])]
    scenes = [('MI-S01', '单次数据流预览', '对照原源拉取与包装迭代器输出', ['MI-U01', 'MI-C01']),
        ('MI-S02', '订单分批导入边界', '区分尾批校验、实际提交与完整导入保证', ['MI-U02', 'MI-D01', 'MI-P01']),
        ('MI-S03', '订单事件与标签去重', '明确首条保留、键和逐次重复事件', ['MI-C02', 'MI-U03']),
        ('MI-S04', '有限回看与恢复', '理解当前缓存位置和持久检查点的责任', ['MI-U04', 'MI-C03'])]
    build_project('more-itertools', {'title': 'More-itertools流式处理工作场景', 'category': '迭代器与数据流',
        'description': '固定真实源码上的取样副作用、严格分批取证、订单去重和有界缓存咨询，九项独立只读任务。'},
        definitions, scenes, materials,
        branches={'MI-D01': [{'id': 'partial-evidence', 'when': 'The actual iterator/options, loop and side-effect or commit boundaries have not been disclosed, the conversation does not say they are unavailable, and the answer reasonably requests a sufficient reproduction.',
            'materials': ['disclosure/partial.py', 'disclosure/partial-events.md']}]},
        extra_entries={'MI-S02': [{'id': 'diagnose_only', 'task_ids': ['MI-D01']},
            {'id': 'unavailable', 'task_ids': ['MI-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
