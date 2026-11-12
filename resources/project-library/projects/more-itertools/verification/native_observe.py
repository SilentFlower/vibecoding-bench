"""观察真实迭代器的源消费、分批副作用、去重及有界缓存。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import more_itertools
from more_itertools import chunked, duplicates_everseen, peekable, seekable, spy, unique_everseen


def preview() -> dict:
    """核原源副作用与返回迭代器保真。@return 预览边界事实。"""
    pulls = []

    def source():
        """提供可观察的一次源。@return 原始元素。"""
        for value in range(5):
            pulls.append(value)
            yield value

    head, replay = spy(source(), 2)
    first_pulls = list(pulls)
    complete = list(replay)
    observed = []

    def another():
        """记录有限peekable拉取。@return 三个字母。"""
        for value in 'ABC':
            observed.append(value)
            yield value

    wrapped = peekable(another())
    truth = bool(wrapped)
    before = list(observed)
    first, last = wrapped.peek(), wrapped[-1]
    return {'spy_preserves_returned_stream': head == [0, 1] and complete == list(range(5)),
        'spy_advances_source_once': first_pulls == [0, 1] and pulls == list(range(5)),
        'peek_and_bool_cache_one': truth and before == ['A'] and first == 'A',
        'negative_index_consumes_remainder': last == 'C' and observed == list('ABC') and list(wrapped) == list('ABC')}


def batching() -> dict:
    """保留strict错误前已经发生的完整批与源消费。@return 分批事实。"""
    pulled, committed, groups = [], [], []

    def source():
        """记录最后不足批次仍被消费。@return 合成订单号。"""
        for value in range(5):
            pulled.append(value)
            yield value

    rejected = False
    try:
        for group in chunked(source(), 2, strict=True):
            groups.append(group)
            committed.extend(group)
    except ValueError:
        rejected = True
    return {'strict_yields_complete_batches_before_error': rejected and groups == [[0, 1], [2, 3]],
        'strict_consumes_incomplete_tail': pulled == list(range(5)),
        'earlier_side_effects_not_rolled_back': committed == [0, 1, 2, 3],
        'default_keeps_partial_batch': list(chunked(range(5), 2)) == [[0, 1], [2, 3], [4]]}


def deduplication() -> dict:
    """实测首条保留和逐次重复记录，不虚构最新值归并。@return 去重事实。"""
    events = [{'order': 'A', 'rev': 1}, {'order': 'A', 'rev': 2},
        {'order': 'B', 'rev': 1}, {'order': 'A', 'rev': 3}]
    first = list(unique_everseen(events, key=lambda row: row['order']))
    repeated = list(duplicates_everseen(events, key=lambda row: row['order']))
    unhashable = False
    try:
        list(unique_everseen([['tea', 'new'], ['tea', 'new']]))
    except TypeError:
        unhashable = True
    labels = [['tea', 'new'], ['tea', 'new'], ['new', 'tea']]
    return {'key_keeps_first_event_in_order': first == [events[0], events[2]],
        'explicit_key_handles_unhashable_labels': unhashable and list(unique_everseen(labels, key=tuple)) == [labels[0], labels[2]],
        'duplicates_keep_every_later_event': repeated == [events[1], events[3]],
        'one_duplicate_per_key_requires_composition': list(unique_everseen(repeated, key=lambda row: row['order'])) == [events[1]]}


def bounded_seek() -> dict:
    """核动态缓存视图与当前窗口相对的seek，不能当持久重放。@return 缓存边界。"""
    stream = seekable('ABCD', maxlen=2)
    view = stream.elements()
    consumed = [next(stream), next(stream), next(stream)]
    before = list(view)
    stream.seek(0)
    replay = [next(stream), next(stream), next(stream)]
    zero = seekable('AB', maxlen=0)
    first = zero.peek()
    return {'bounded_seek_zero_uses_current_cache': consumed == list('ABC') and before == list('BC') and replay == list('BCD'),
        'sequence_view_tracks_cache_eviction': list(view) == list('CD'),
        'zero_cache_peek_preserves_next': first == 'A' and next(zero) == 'A' and list(zero.elements()) == []}


def main() -> None:
    """仅输出当前任务已声明的实际观察。@return None。"""
    fields = {
        'MI-U01': ('spy_preserves_returned_stream', 'spy_advances_source_once'),
        'MI-C01': ('peek_and_bool_cache_one', 'negative_index_consumes_remainder'),
        'MI-U02': ('strict_yields_complete_batches_before_error', 'strict_consumes_incomplete_tail', 'default_keeps_partial_batch'),
        'MI-P01': ('strict_yields_complete_batches_before_error', 'earlier_side_effects_not_rolled_back'),
        'MI-C02': ('key_keeps_first_event_in_order', 'explicit_key_handles_unhashable_labels'),
        'MI-U03': ('duplicates_keep_every_later_event', 'one_duplicate_per_key_requires_composition'),
        'MI-U04': ('bounded_seek_zero_uses_current_cache', 'sequence_view_tracks_cache_eviction'),
        'MI-C03': ('bounded_seek_zero_uses_current_cache', 'zero_cache_peek_preserves_next')}
    task = sys.argv[1]
    if task in ('MI-U01', 'MI-C01'):
        facts = preview()
    elif task in ('MI-U02', 'MI-P01'):
        facts = batching()
    elif task in ('MI-C02', 'MI-U03'):
        facts = deduplication()
    else:
        facts = bounded_seek()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(more_itertools.__file__).resolve() == root / 'library/more_itertools/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
