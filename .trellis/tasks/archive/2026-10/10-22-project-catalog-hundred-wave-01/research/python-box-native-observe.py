"""独立观察Box属性、默认副作用、覆盖、点键和配置转换。"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import box
from box import Box, BoxError, BoxKeyError, ConfigBox


def attributes() -> dict:
    """核属性便利不改变原键或消除名称碰撞。@return 属性事实。"""
    value = Box({'items': ['A'], 'first name': 'Ada'})
    collisions = Box({'a-b': 1, 'a b': 2})
    rejected = False
    try:
        Box({'a-b': 1, 'a b': 2}, box_duplicates='error')
    except BoxError:
        rejected = True
    exact = Box({'a-b': 1, 'a b': 2}, conversion_box=False)
    return {'attributes_keep_original_keys_and_dictionary_methods': callable(value.items)
            and value['items'] == ['A'] and value.first_name == 'Ada'
            and set(value.keys()) == {'items', 'first name'},
        'conversion_collisions_can_be_rejected_or_bypassed_explicitly': collisions['a-b'] == 1
            and collisions['a b'] == 2 and collisions.a_b == 2 and rejected
            and exact['a-b'] == 1 and exact['a b'] == 2}


def missing_values() -> dict:
    """核默认读取的原地创建与已有只查找控制。@return 默认事实。"""
    creating = Box(default_box=True)
    ignored = creating.customer.region
    explicit = Box(default_box=True)
    explicit_result = explicit.get('customer', None)
    detached = Box(default_box=True, default_box_create_on_get=False)
    detached_value = detached.customer.region
    strict_failure = False
    try:
        Box().customer
    except BoxKeyError:
        strict_failure = True
    return {'default_reads_can_create_nested_configuration': creating.to_dict() == {'customer': {'region': {}}}
            and isinstance(ignored, Box),
        'explicit_get_and_noncreating_default_do_not_validate_required_fields': explicit_result is None
            and explicit.to_dict() == {} and detached.to_dict() == {} and isinstance(detached_value, Box)
            and strict_failure}


def overlays() -> dict:
    """核浅覆盖、递归合并和独立列表政策。@return 覆盖事实。"""
    base = {'db': {'host': 'A', 'port': 5432}, 'tags': ['base']}
    override = {'db': {'host': 'B'}, 'tags': ['new', 'new']}
    shallow = Box(deepcopy(base))
    shallow.update(deepcopy(override))
    merged = Box(deepcopy(base))
    merged.merge_update(deepcopy(override))
    extended = Box(deepcopy(base))
    extended.merge_update(deepcopy(override), box_merge_lists='extend')
    unique = Box(deepcopy(base))
    unique.merge_update(deepcopy(override), box_merge_lists='unique')
    return {'existing_recursive_merge_and_list_policy_are_distinct': shallow.to_dict()['db'] == {'host': 'B'}
        and merged.to_dict()['db'] == {'host': 'B', 'port': 5432} and merged.tags == ['new', 'new']
        and extended.tags == ['base', 'new', 'new'] and unique.tags == ['base', 'new']
        and base == {'db': {'host': 'A', 'port': 5432}, 'tags': ['base']}}


def dotted_keys() -> dict:
    """核构造时点键已经参与路径写入，不能假设原键仍被保存。@return 路径事实。"""
    source = {'db.host': 'flat', 'db': {'host': 'nested'}}
    missing_parent_rejected = False
    try:
        Box(source, box_dots=True)
    except BoxKeyError:
        missing_parent_rejected = True
    combined = Box(source, box_dots=True, default_box=True)
    literal = Box(source)
    excluded = Box(source, box_dots=True, box_dots_exclude=r'^db\.host$')
    reversed_input = Box({'db': {'host': 'nested'}, 'db.host': 'flat'}, box_dots=True)
    nested = Box({'db': {'host': 'nested'}}, box_dots=True)
    disabled = Box({'db': {'host': 'nested'}})
    rejected = False
    try:
        disabled['db.host']
    except BoxKeyError:
        rejected = True
    return {'dotted_key_observations': {'combined': combined.to_dict(), 'literal': literal.to_dict(),
            'excluded': excluded.to_dict(), 'reversed': reversed_input.to_dict(), 'source': source,
            'nested_lookup': nested['db.host'], 'disabled_rejected': rejected,
            'missing_parent_rejected': missing_parent_rejected},
        'dotted_input_keys_require_explicit_construction_policy': missing_parent_rejected
        and combined.to_dict() == {'db': {'host': 'nested'}}
        and combined['db.host'] == 'nested' and reversed_input['db']['host'] == 'flat'
        and literal['db.host'] == excluded['db.host'] == 'flat'
        and literal['db']['host'] == excluded['db']['host'] == 'nested'
        and nested['db.host'] == 'nested' and rejected and source['db.host'] == 'flat'}


def configuration_casts() -> dict:
    """核近似布尔转换不提供严格业务词汇校验。@return 转换事实。"""
    values = ConfigBox({'disabled': 'false', 'spaced': ' FALSE ', 'unknown': 'maybe', 'count': '5', 'bad': 'five'})
    rejected = False
    try:
        values.int('bad')
    except ValueError:
        rejected = True
    return {'config_casting_is_approximate_not_a_strict_schema': values.bool('disabled') is False
        and values.bool('spaced') is True and values.bool('unknown') is True
        and values.int('count') == 5 and rejected and values['count'] == '5'}


def main() -> None:
    """核真实纯Python候选并输出当前任务断言。@return None。"""
    entries = {'BX-U01': (attributes, ['attributes_keep_original_keys_and_dictionary_methods']),
        'BX-C01': (attributes, ['conversion_collisions_can_be_rejected_or_bypassed_explicitly']),
        'BX-U02': (missing_values, ['default_reads_can_create_nested_configuration']),
        'BX-P01': (missing_values, ['explicit_get_and_noncreating_default_do_not_validate_required_fields']),
        'BX-C02': (overlays, ['existing_recursive_merge_and_list_policy_are_distinct']),
        'BX-U03': (dotted_keys, ['dotted_input_keys_require_explicit_construction_policy']),
        'BX-C03': (configuration_casts, ['config_casting_is_approximate_not_a_strict_schema'])}
    observe, fields = entries[sys.argv[1]]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(box.__file__).resolve() == root / 'library/box/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
