"""观察Dpath路径协议、副作用和过滤删除的实际边界。"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import dpath
from dpath import MergeType, delete, get, merge, new, search
from dpath import set as set_path
from dpath.exceptions import PathNotFound


def lookups() -> dict:
    """核单结果约束、默认值和含分隔符键。@return 查询事实。"""
    values = {'a': 1, 'b': 2}
    missing = object()
    ambiguous = False
    try:
        get(values, '*', default=missing)
    except ValueError:
        ambiguous = True
    absent = get(values, 'missing', default=missing)
    paths = {'a/b': {'x': 1}, 'a': {'b': {'x': 2}}}
    return {'get_default_handles_absence_but_not_multiple_matches': absent is missing and ambiguous
            and get(values, '/') is values and get(values, '') is values,
        'segment_sequence_preserves_a_key_containing_separator': get(paths, 'a/b/x') == 2
            and get(paths, ['a/b', 'x']) == 1}


def writes() -> dict:
    """核已有路径更新与字面新建的不同合同。@return 修改事实。"""
    value = {'orders': [{'state': 'old'}, {'state': 'old'}]}
    changed = set_path(value, 'orders/*/state', 'new')
    absent = set_path(value, 'missing/name', 'value')
    created = {}
    result = new(created, 'literal*/0/id', 'A')
    return {'set_updates_existing_matches_while_new_creates_literal_structure': changed == 2 and absent == 0
        and value == {'orders': [{'state': 'new'}, {'state': 'new'}]}
        and result is created and created == {'literal*': [{'id': 'A'}]}}


def sequence_delete() -> dict:
    """核非尾列表删除保留索引，以及无匹配异常。@return 删除事实。"""
    value = {'xs': ['A', 'B', 'C']}
    middle = delete(value, 'xs/1')
    middle_value = deepcopy(value)
    tail = delete(value, 'xs/2')
    absent = False
    try:
        delete(value, 'missing')
    except PathNotFound:
        absent = True
    return {'list_delete_keeps_non_tail_holes_and_missing_raises': middle == tail == 1
        and middle_value == {'xs': ['A', None, 'C']} and value == {'xs': ['A', None]} and absent}


def selection() -> dict:
    """核树形投影和路径值迭代两种已有结果。@return 选择事实。"""
    value = {'items': [{'id': 'A', 'hidden': 'private'}, {'id': 'B'}]}
    tree = search(value, 'items/*/id')
    records = list(search(value, 'items/*/id', yielded=True))
    return {'search_can_return_structured_projection_or_path_value_records':
        tree == {'items': [{'id': 'A'}, {'id': 'B'}]}
        and records == [('items/0/id', 'A'), ('items/1/id', 'B')]
        and value['items'][0]['hidden'] == 'private'}


def merges() -> dict:
    """核列表政策、源引用和类型失败后的部分更新。@return 合并事实。"""
    target, source = {}, {'tags': ['A']}
    merge(target, source)
    result = merge(target, {'tags': ['B']})
    replaced = merge({'tags': ['A']}, {'tags': ['B']}, flags=MergeType.REPLACE)
    partial = {'later': 1}
    failed = False
    try:
        merge(partial, {'added': 2, 'later': 'bad'}, flags=MergeType.TYPESAFE)
    except TypeError:
        failed = True
    baseline = {'later': 1}
    isolated = deepcopy(baseline)
    try:
        merge(isolated, deepcopy({'added': 2, 'later': 'bad'}), flags=MergeType.TYPESAFE)
    except TypeError:
        pass
    return {'merge_list_policy_and_source_aliasing_are_explicit': result is target
            and source['tags'] == ['A', 'B'] and target['tags'] is source['tags']
            and replaced == {'tags': ['B']},
        'typesafe_failure_does_not_roll_back_prior_mutation': failed and partial == {'later': 1, 'added': 2}
            and baseline == {'later': 1} and isolated == {'later': 1, 'added': 2}}


def filtered_delete() -> dict:
    """用独立正反矩阵验证值筛选始终受路径约束。@return 修复验收事实。"""
    checks = []
    for separator in ['/', '.']:
        value = {'selected': {'drop': 1, 'keep': 0}, 'outside': {'same': 1}}
        count = delete(value, 'selected' + separator + '*', separator=separator, afilter=lambda item: item == 1)
        checks.append(count == 1 and value == {'selected': {'keep': 0}, 'outside': {'same': 1}})
    value = {'selected': {'keep': 0}, 'outside': {'same': 1}}
    absent = False
    try:
        delete(value, 'selected/*', afilter=lambda item: item == 1)
    except PathNotFound:
        absent = True
    checks.append(absent and value == {'selected': {'keep': 0}, 'outside': {'same': 1}})
    value = {'selected': {'drop': 1, 'keep': 0}, 'outside': {'same': 1}}
    checks.append(delete(value, 'selected/*') == 2 and value == {'selected': {}, 'outside': {'same': 1}})
    return {'filtered_delete_intersects_glob_and_predicate_without_changing_unfiltered_behavior': all(checks)}


def main() -> None:
    """核真实候选导入并仅输出当前任务验收字段。@return None。"""
    entries = {'DP-U01': (lookups, 'get_default_handles_absence_but_not_multiple_matches'),
        'DP-C01': (lookups, 'segment_sequence_preserves_a_key_containing_separator'),
        'DP-U02': (writes, 'set_updates_existing_matches_while_new_creates_literal_structure'),
        'DP-U03': (sequence_delete, 'list_delete_keeps_non_tail_holes_and_missing_raises'),
        'DP-C02': (selection, 'search_can_return_structured_projection_or_path_value_records'),
        'DP-U04': (merges, 'merge_list_policy_and_source_aliasing_are_explicit'),
        'DP-P01': (merges, 'typesafe_failure_does_not_roll_back_prior_mutation'),
        'DP-M01': (filtered_delete, 'filtered_delete_intersects_glob_and_predicate_without_changing_unfiltered_behavior')}
    observe, field = entries[sys.argv[1]]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(dpath.__file__).resolve() == root / 'library/dpath/__init__.py',
        field: observe()[field]}))


if __name__ == '__main__':
    main()
