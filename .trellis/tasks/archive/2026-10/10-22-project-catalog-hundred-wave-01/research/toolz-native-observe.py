"""观察真实Toolz组合、惰性、缓存键、分组与浅合并。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import toolz
from toolz import compose, groupby, memoize, merge, merge_with, partition, partition_all, pipe, reduceby
from toolz.curried import map as curried_map


def pipelines() -> dict:
    """核执行顺序与保留尾批，不把curry当成物化。@return 管道事实。"""
    calls = []

    def double(value):
        """记录实际元素处理。@param value 原值。@return 两倍值。"""
        calls.append(value)
        return value * 2

    mapped = curried_map(double)(iter(range(1, 6)))
    deferred = calls == []
    chunks = list(partition_all(2, mapped))
    return {'compose_and_pipe_have_distinct_order': compose(lambda value: value * 2, lambda value: value + 1)(3) == 8
            and pipe(3, lambda value: value * 2, lambda value: value + 1) == 7,
        'curried_map_remains_lazy': deferred and calls == [1, 2, 3, 4, 5],
        'partition_all_preserves_partial_tail': chunks == [(2, 4), (6, 8), (10,)]
            and list(partition(2, [2, 4, 6, 8, 10])) == [(2, 4), (6, 8)]}


def cache_keys() -> dict:
    """核默认哈希要求和真实(args,kwargs)键接口。@return 价格缓存事实。"""
    calls = []

    def price(items, discount=0):
        """计算合成纯价格并记录控制端调用次数。@param items 明确数量列表。@param discount 折扣。@return 计算结果。"""
        calls.append((tuple(items), discount))
        return sum(items) - discount

    rejected = False
    try:
        memoize(price)([1, 2, 3], discount=1)
    except TypeError:
        rejected = True
    initial_calls = list(calls)

    def key(args, kwargs):
        """按实际接口保留全部价格语义。@param args 位置实参。@param kwargs 关键字实参。@return 可哈希业务键。"""
        discount = args[1] if len(args) > 1 else kwargs.get('discount', 0)
        return tuple(args[0]), discount

    cached = memoize(price, key=key)
    first = cached([1, 2, 3], discount=1)
    repeated = cached([1, 2, 3], 1)
    different = cached([1, 2, 3], discount=2)
    return {'default_memoize_requires_hashable_arguments': rejected and initial_calls == [],
        'custom_key_receives_args_kwargs_and_preserves_inputs': first == repeated == 5 and different == 4
            and calls == [((1, 2, 3), 1), ((1, 2, 3), 2)]}


def cache_lifetime() -> dict:
    """用显式外部状态展示自动失效并不存在。@return 缓存生命周期事实。"""
    unit_price = [2]
    cache = {}

    def quote(qty):
        """读取合成可变价格，供反例而非纯函数推荐。@param qty 数量。@return 实际报价。"""
        return qty * unit_price[0]

    cached = memoize(quote, cache=cache)
    first = cached(2)
    unit_price[0] = 3
    stale = cached(2)
    cache.clear()
    refreshed = cached(2)
    return {'external_state_change_does_not_invalidate_cache': first == stale == 4 and refreshed == 6}


def grouped_totals() -> dict:
    """核全流收集和已有按键归约。@return 区域统计事实。"""
    rows = [{'region': 'east', 'qty': 1}, {'region': 'west', 'qty': 2}, {'region': 'east', 'qty': 3}]
    pulled = []

    def source():
        """记录groupby的真实全量消费。@return 合成订单。"""
        for row in rows:
            pulled.append(row['region'])
            yield row

    grouped = groupby('region', source())
    totals = reduceby('region', lambda total, row: total + row['qty'], iter(rows), init=0)
    return {'groupby_collects_nonadjacent_full_groups': pulled == ['east', 'west', 'east']
            and grouped == {'east': [rows[0], rows[2]], 'west': [rows[1]]},
        'existing_reduceby_keeps_only_business_accumulators': totals == {'east': 4, 'west': 2}
            and all(isinstance(value, int) for value in totals.values())}


def mapping_merge() -> dict:
    """核新外层映射、共享嵌套值和同键账单归并。@return 合并事实。"""
    base = {'theme': 'light', 'options': {'labels': ['a']}}
    override = {'theme': 'dark'}
    combined = merge(base, override)
    untouched = base['theme'] == 'light' and combined['theme'] == 'dark' and combined is not base
    shared = combined['options'] is base['options']
    combined['options']['labels'].append('b')
    first, second = {'A': 2, 'B': 3}, {'A': 5, 'C': 7}
    replaced = merge(first, second)
    summed = merge_with(sum, first, second)
    return {'merge_is_new_shallow_mapping_with_later_precedence': untouched and shared and base['options']['labels'] == ['a', 'b'],
        'merge_with_aggregates_all_same_key_values': replaced == {'A': 5, 'B': 3, 'C': 7}
            and summed == {'A': 7, 'B': 3, 'C': 7} and first == {'A': 2, 'B': 3} and second == {'A': 5, 'C': 7}}


def main() -> None:
    """核实际候选并输出本任务业务事实。@return None。"""
    task = sys.argv[1]
    fields = {'TZ-U01': ('compose_and_pipe_have_distinct_order',),
        'TZ-C01': ('curried_map_remains_lazy', 'partition_all_preserves_partial_tail'),
        'TZ-U02': ('default_memoize_requires_hashable_arguments', 'custom_key_receives_args_kwargs_and_preserves_inputs'),
        'TZ-C02': ('external_state_change_does_not_invalidate_cache',),
        'TZ-U03': ('groupby_collects_nonadjacent_full_groups',),
        'TZ-C03': ('existing_reduceby_keeps_only_business_accumulators',),
        'TZ-U04': ('merge_is_new_shallow_mapping_with_later_precedence',),
        'TZ-C04': ('merge_with_aggregates_all_same_key_values',)}
    if task in ('TZ-U01', 'TZ-C01'):
        facts = pipelines()
    elif task == 'TZ-U02':
        facts = cache_keys()
    elif task == 'TZ-C02':
        facts = cache_lifetime()
    elif task in ('TZ-U03', 'TZ-C03'):
        facts = grouped_totals()
    else:
        facts = mapping_merge()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(toolz.__file__).resolve() == root / 'library/toolz/__init__.py',
        **{field: facts[field] for field in fields[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
