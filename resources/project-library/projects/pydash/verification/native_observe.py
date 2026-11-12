"""独立观察Pydash缺失值、深路径、原地合并和嵌套投影。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pydash
from pydash import clone_deep, get, has, merge, merge_with, omit, pick, set_


def lookups() -> dict:
    """核存在性和路径分词分别属于不同业务决定。@return 查询事实。"""
    missing = object()
    values = {'nil': None, 'disabled': False, 'count': 0}
    paths = {'a.b': {'value': 1}, 'a': {'b': {'value': 2}}}
    return {'explicit_missing_sentinel_distinguishes_present_falsey_values': get(values, 'nil', missing) is None
            and get(values, 'disabled', missing) is False and get(values, 'count', missing) == 0
            and get(values, 'missing', missing) is missing and has(values, 'nil') and not has(values, 'missing'),
        'path_list_preserves_a_literal_dot_key': get(paths, 'a.b.value') == 2
            and get(paths, ['a.b', 'value']) == 1}


def writing_paths() -> dict:
    """核写路径创建结构和对原对象的所有权。@return 写入事实。"""
    bracket, dotted = {}, {}
    result = set_(bracket, 'orders[0].id', 'A')
    set_(dotted, 'orders.0.id', 'A')
    baseline = {'orders': [{'id': 'A'}]}
    isolated = clone_deep(baseline)
    set_(isolated, 'orders[0].id', 'B')
    return {'set_is_in_place_and_index_syntax_controls_created_shape': result is bracket
            and bracket == {'orders': [{'id': 'A'}]} and dotted == {'orders': {'0': {'id': 'A'}}},
        'deep_clone_can_isolate_a_declared_update': baseline == {'orders': [{'id': 'A'}]}
            and isolated == {'orders': [{'id': 'B'}]} and isolated['orders'] is not baseline['orders']}


def merge_ownership() -> dict:
    """核目标原地修改、源复制和显式列表策略。@return 合并事实。"""
    baseline = {'nested': {'keep': 1}, 'values': [1, 2]}
    source = {'nested': {'added': 2}, 'values': [9], 'fresh': {'x': 1}}
    result = merge(baseline, source)
    result['fresh']['x'] = 7

    def concatenate(left, right, key, destination, incoming):
        """只覆盖列表政策，其他值委托原生合并。@param left 目标值。@param right 源值。@param key 键。@param destination 目标映射。@param incoming 源映射。@return 合并值或None。"""
        return left + right if isinstance(left, list) and isinstance(right, list) else None

    combined = merge_with({'tags': ['a']}, {'tags': ['b']}, iteratee=concatenate)
    delegated = merge_with({'limit': 5}, {'limit': 7}, iteratee=lambda left, right: None)
    explicit_zero = merge_with({'limit': 5}, {'limit': 7}, iteratee=lambda left, right: 0)
    return {'merge_mutates_destination_and_merges_lists_by_index': result is baseline
            and result['nested'] == {'keep': 1, 'added': 2} and result['values'] == [9, 2]
            and source == {'nested': {'added': 2}, 'values': [9], 'fresh': {'x': 1}},
        'custom_merge_uses_none_as_delegate_and_keeps_falsey_results': combined == {'tags': ['a', 'b']}
            and delegated == {'limit': 7} and explicit_zero == {'limit': 0}}


def public_projection() -> dict:
    """核顶层选择不会自动裁掉嵌套字段，深路径投影已有支持。@return 投影事实。"""
    profile = {'name': 'Ada', 'password': 'synthetic-password',
        'contact': {'email': 'a@example.test', 'token': 'synthetic-private-token'}}
    whole = pick(profile, 'name', 'contact')
    allowed = pick(profile, 'name', 'contact.email')
    removed = omit(profile, 'password', 'contact.token')
    return {'nested_projection_boundary_must_be_explicit': whole['contact']['token'] == 'synthetic-private-token'
        and whole['contact'] is profile['contact']
        and allowed == removed == {'name': 'Ada', 'contact': {'email': 'a@example.test'}}
        and 'token' in profile['contact'] and 'password' in profile
        and removed['contact'] is not profile['contact']}


def main() -> None:
    """核src候选绑定并输出精确业务字段。@return None。"""
    entries = {'PD-U01': (lookups, ['explicit_missing_sentinel_distinguishes_present_falsey_values']),
        'PD-C01': (lookups, ['path_list_preserves_a_literal_dot_key']),
        'PD-U02': (writing_paths, ['set_is_in_place_and_index_syntax_controls_created_shape']),
        'PD-P01': (writing_paths, ['deep_clone_can_isolate_a_declared_update']),
        'PD-U03': (merge_ownership, ['merge_mutates_destination_and_merges_lists_by_index']),
        'PD-C02': (merge_ownership, ['custom_merge_uses_none_as_delegate_and_keeps_falsey_results']),
        'PD-C03': (public_projection, ['nested_projection_boundary_must_be_explicit'])}
    observe, fields = entries[sys.argv[1]]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(pydash.__file__).resolve() == root / 'library/src/pydash/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
