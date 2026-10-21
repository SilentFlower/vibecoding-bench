"""观察DeepDiff比较政策、结构化路径和双向Delta。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

# NumPy等后台线程遵守本仓冻结资源设置，不改变候选实现或比较算法。
os.environ.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', POLARS_MAX_THREADS='2', MALLOC_ARENA_MAX='2')

import deepdiff
from deepdiff import DeepDiff, Delta
from deepdiff.delta import DeltaError


def repetition() -> dict:
    """核无序和重复次数是独立比较政策。@return 实际事实。"""
    before, after = [1, 1, 2], [1, 2, 2]
    ignored = DeepDiff(before, after, ignore_order=True)
    counted = DeepDiff(before, after, ignore_order=True, report_repetition=True)
    rows = counted.get('repetition_change', {}).values()
    changes = {row['value']: (row['old_repeat'], row['new_repeat']) for row in rows}
    return {'unordered_equality_can_ignore_multiplicity_unless_requested': ignored == {}
        and changes == {1: (2, 1), 2: (1, 2)} and before == [1, 1, 2] and after == [1, 2, 2]}


def grouping() -> dict:
    """核唯一身份对齐与重复键折叠的区别。@return 实际事实。"""
    unique = [{'id': 'A', 'qty': 1}, {'id': 'B', 'qty': 2}]
    reordered = list(reversed(unique))
    old = [{'id': 'A', 'qty': 1}, {'id': 'A', 'qty': 2}]
    new = [{'id': 'A', 'qty': 99}, {'id': 'A', 'qty': 2}]
    collapsed = DeepDiff(old, new, group_by='id')
    retained = DeepDiff(old, new, group_by='id', group_by_sort_key='qty')
    return {'group_identity_requires_a_deliberate_duplicate_key_policy':
        DeepDiff(unique, reordered, group_by='id') == {} and collapsed == {} and bool(retained)
        and old == [{'id': 'A', 'qty': 1}, {'id': 'A', 'qty': 2}]}


def numeric_policy() -> dict:
    """核忽略数字类型不会忽略不同数值。@return 实际事实。"""
    strict = DeepDiff({'price': 10}, {'price': 10.0})
    same_value = DeepDiff({'price': 10}, {'price': 10.0}, ignore_numeric_type_changes=True)
    changed = DeepDiff({'price': 10}, {'price': 10.5}, ignore_numeric_type_changes=True)
    return {'ignore_numeric_type_changes_preserves_real_value_differences':
        'type_changes' in strict and same_value == {} and 'values_changed' in changed}


def exclusion() -> dict:
    """核精确排除易变字段但保留订单业务变化。@return 实际事实。"""
    before = {'order': {'qty': 1}, 'updated_at': 'old'}
    after = {'order': {'qty': 2}, 'updated_at': 'new'}
    diff = DeepDiff(before, after, exclude_paths=["root['updated_at']"])
    return {'exact_exclusion_keeps_other_business_changes_and_inputs': diff == {
        'values_changed': {"root['order']['qty']": {'old_value': 1, 'new_value': 2}}}
        and before['updated_at'] == 'old' and after['updated_at'] == 'new'}


def structured_paths() -> dict:
    """核树形节点提供真实路径段和前后值，无需执行路径文本。@return 实际事实。"""
    diff = DeepDiff({'a/b': {'qty': 1}}, {'a/b': {'qty': 2}}, view='tree')
    rows = list(diff['values_changed'])
    return {'tree_nodes_expose_typed_path_segments_and_before_after_values': len(rows) == 1
        and rows[0].path(output_format='list') == ['a/b', 'qty']
        and rows[0].t1 == 1 and rows[0].t2 == 2}


def delta_preview() -> dict:
    """核默认非原地双向应用与显式原值错误拒绝。@return 实际事实。"""
    before = {'qty': 1, 'items': ['A']}
    after = {'qty': 2, 'items': ['A', 'B']}
    delta = Delta(DeepDiff(before, after), bidirectional=True, raise_errors=True, log_errors=False)
    forward = before + delta
    backward = forward - delta
    rejected = False
    try:
        {'qty': 9, 'items': ['A']} + delta
    except DeltaError:
        rejected = True
    return {'bidirectional_delta_roundtrip_is_copied_and_old_value_guard_is_explicit':
        forward == after and backward == before and before == {'qty': 1, 'items': ['A']}
        and forward is not before and rejected}


def main() -> None:
    """核真实候选文件并输出精确字段。@return None。"""
    entries = {'DD-U01': (repetition, 'unordered_equality_can_ignore_multiplicity_unless_requested'),
        'DD-C01': (grouping, 'group_identity_requires_a_deliberate_duplicate_key_policy'),
        'DD-U02': (numeric_policy, 'ignore_numeric_type_changes_preserves_real_value_differences'),
        'DD-C02': (exclusion, 'exact_exclusion_keeps_other_business_changes_and_inputs'),
        'DD-C03': (structured_paths, 'tree_nodes_expose_typed_path_segments_and_before_after_values'),
        'DD-P01': (delta_preview, 'bidirectional_delta_roundtrip_is_copied_and_old_value_guard_is_explicit')}
    observe, field = entries[sys.argv[1]]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(deepdiff.__file__).resolve() == root / 'library/deepdiff/__init__.py',
        field: observe()[field]}))


if __name__ == '__main__':
    main()
