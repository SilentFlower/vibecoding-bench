"""观察真实PETL惰性、错误策略、关联基数及临时CSV往返。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import petl as etl
from petl.errors import FieldSelectionError


def lazy_views() -> dict:
    """对照可重读源和一次源，不把视图当快照。@return 消费与重读事实。"""
    data = [('sku', 'qty'), ('001', '2'), ('002', '3')]
    calls = []

    class Source:
        """提供明确可重用的合成表源。"""

        def __iter__(self):
            """记录每次真实迭代。@return 当前表行迭代器。"""
            calls.append('read')
            return iter(data)

    view = etl.convert(Source(), 'qty', int)
    deferred = calls == []
    first, second = view.list(), view.list()
    data[1] = ('001', '7')
    changed = view.list()
    explicit_reads = list(calls)
    list(etl.convert(Source(), 'qty', int))
    builtin_reads_twice = len(calls) - len(explicit_reads) == 2
    one_shot = etl.convert(iter(data), 'qty', int)
    once = one_shot.list()
    exhausted = False
    try:
        one_shot.list()
    except FieldSelectionError:
        exhausted = True
    first_builtin_failed = False
    try:
        list(etl.convert(iter(data), 'qty', int))
    except FieldSelectionError:
        first_builtin_failed = True
    return {'convert_view_is_lazy_and_reiterates_source': deferred and explicit_reads == ['read', 'read', 'read']
            and first == second == [('sku', 'qty'), ('001', 2), ('002', 3)]
            and changed[1] == ('001', 7),
        'one_shot_source_is_not_a_replay_cache': once[1] == ('001', 7) and exhausted,
        'builtin_list_length_hint_adds_a_traversal': builtin_reads_twice and first_builtin_failed}


def conversions() -> dict:
    """核真实迭代时的替代、拒绝和异常对象策略。@return 转换事实。"""
    rows = [('sku', 'qty'), ('001', '2'), ('002', 'bad')]
    default = list(etl.convert(rows, 'qty', int))
    marked = list(etl.convert(rows, 'qty', int, errorvalue='invalid'))
    inline = list(etl.convert(rows, 'qty', int, failonerror='inline'))
    strict = etl.convert(rows, 'qty', int, failonerror=True)
    iterator = iter(strict)
    prefix = [next(iterator), next(iterator)]
    rejected = False
    try:
        next(iterator)
    except ValueError:
        rejected = True
    return {'conversion_error_policies_are_explicit': default == [('sku', 'qty'), ('001', 2), ('002', None)]
            and marked[2] == ('002', 'invalid') and isinstance(inline[2][1], ValueError),
        'strict_conversion_fails_during_consumption': rejected and prefix == [('sku', 'qty'), ('001', 2)]}


def joins() -> dict:
    """核重复价格键的匹配组合与缺失值。@return 实际关联基数。"""
    left = [('sku', 'qty'), ('A', 1), ('A', 2), ('B', 3)]
    right = [('sku', 'price'), ('A', 10), ('A', 20)]
    inner, outer = list(etl.join(left, right, key='sku')), list(etl.leftjoin(left, right, key='sku'))
    combinations = {('A', 1, 10), ('A', 1, 20), ('A', 2, 10), ('A', 2, 20)}
    return {'duplicate_keys_produce_all_matching_combinations': inner[0] == ('sku', 'qty', 'price')
            and len(inner) == 5 and set(inner[1:]) == combinations,
        'left_join_preserves_unmatched_row': outer[0] == inner[0] and len(outer) == 6
            and set(outer[1:]) == combinations | {('B', 3, None)}}


def csv_roundtrip() -> dict:
    """只读写专用临时CSV，核值类型和缺失编码界限。@return CSV事实。"""
    with TemporaryDirectory(prefix='petl-exchange-') as directory:
        source, target, nulls = (Path(directory) / name for name in ('source.csv', 'target.csv', 'nulls.csv'))
        source.write_text('sku,qty,label\n001,2,"茶,hot"\n002,3,coffee\n', encoding='utf-8')
        rows = list(etl.fromcsv(str(source), encoding='utf-8'))
        converted = list(etl.convert(rows, 'qty', int, failonerror=True))
        etl.tocsv(rows, str(target), encoding='utf-8', lineterminator='\n')
        reread = list(etl.fromcsv(str(target), encoding='utf-8'))
        etl.tocsv([('id', 'value'), ('A', None), ('B', '')], str(nulls), encoding='utf-8')
        nulled = list(etl.fromcsv(str(nulls), encoding='utf-8'))
        return {'csv_reads_strings_and_preserves_selected_fields': rows[1] == ('001', '2', '茶,hot')
                and converted[1] == ('001', 2, '茶,hot') and reread == rows,
            'plain_csv_collapses_none_and_empty_string': nulled == [('id', 'value'), ('A', ''), ('B', '')]}


def main() -> None:
    """输出当前独立任务事实并核候选导入。@return None。"""
    task = sys.argv[1]
    fields = {'PE-U01': ('convert_view_is_lazy_and_reiterates_source', 'builtin_list_length_hint_adds_a_traversal'),
        'PE-C01': ('one_shot_source_is_not_a_replay_cache', 'builtin_list_length_hint_adds_a_traversal'),
        'PE-U02': ('conversion_error_policies_are_explicit',),
        'PE-C02': ('strict_conversion_fails_during_consumption',),
        'PE-U03': ('duplicate_keys_produce_all_matching_combinations', 'left_join_preserves_unmatched_row'),
        'PE-C03': ('duplicate_keys_produce_all_matching_combinations',),
        'PE-U04': ('csv_reads_strings_and_preserves_selected_fields',),
        'PE-P01': ('csv_reads_strings_and_preserves_selected_fields', 'plain_csv_collapses_none_and_empty_string')}
    if task in ('PE-U01', 'PE-C01'):
        facts = lazy_views()
    elif task in ('PE-U02', 'PE-C02'):
        facts = conversions()
    elif task in ('PE-U03', 'PE-C03'):
        facts = joins()
    else:
        facts = csv_roundtrip()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(etl.__file__).resolve() == root / 'library/petl/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
