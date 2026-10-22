"""观察有序容器的重复值、视图、边界、键缓存及分页事实。"""
from bisect import bisect_left
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import sortedcontainers
from sortedcontainers import SortedDict, SortedKeyList, SortedList, SortedSet


def main() -> None:
    """仅操作进程内合成容器，不修改候选文件。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(sortedcontainers.__file__).resolve() == root / 'library/src/sortedcontainers/__init__.py'}
    task = argv[1]
    if task == 'SC-U01':
        values = [3, 1, 3, 2]
        result['sorted_list_multiplicity_and_set_uniqueness_are_different_contracts'] = (
            list(SortedList(values)) == [1, 2, 3, 3]
            and list(SortedSet(values)) == [1, 2, 3])
    elif task == 'SC-U02':
        mapping = SortedDict({3: 'A', 1: 'Z', 2: 'B', 4: 'Y'})
        view = mapping.values()
        snapshot = list(view)
        del mapping.keys()[1:3]
        result['ordered_views_are_live_and_rank_deletion_changes_the_mapping'] = (
            snapshot == ['Z', 'B', 'A', 'Y'] and list(view) == ['Z', 'Y']
            and list(mapping.items()) == [(1, 'Z'), (4, 'Y')])
    elif task == 'SC-C01':
        values = SortedList([1, 3, 3, 5])
        lower = values.bisect_left(3)
        upper = values.bisect_right(3)
        insertion = values.bisect_left(4)
        result['neighbor_queries_require_distinct_bisect_sides_and_edge_guards'] = (
            (values[lower - 1], values[upper], values[insertion - 1], values[insertion]) == (1, 5, 3, 5)
            and values.bisect_left(0) == 0 and values.bisect_right(6) == len(values)
            and bisect_left([], 4) == 0)
    elif task == 'SC-C02':
        first, second = {'id': 'A', 'rank': 1}, {'id': 'B', 'rank': 2}
        records = SortedKeyList([first, second], key=lambda item: item['rank'])
        first['rank'] = 3
        repaired = SortedKeyList(records, key=lambda item: item['rank'])
        result['mutating_a_stored_sort_key_does_not_refresh_the_cached_index'] = (
            [item['rank'] for item in records] == [3, 2]
            and [item['id'] for item in repaired] == ['B', 'A']
            and records.bisect_key_right(2) == 2)
    elif task == 'SC-P01':
        data = [{'id': value, 'rank': 1 if value < 4 else 2} for value in (1, 2, 3, 4)]
        by_rank = SortedKeyList(data, key=lambda item: item['rank'])
        by_identity = SortedKeyList(data, key=lambda item: (item['rank'], item['id']))
        first = by_rank[:2]
        naive = by_rank[by_rank.bisect_key_right(first[-1]['rank']):]
        complete = by_identity[by_identity.bisect_key_right((1, 2)):]
        result['pagination_needs_a_stable_tie_breaker_and_explicit_snapshot_policy'] = (
            [item['id'] for item in first] == [1, 2]
            and [item['id'] for item in naive] == [4]
            and [item['id'] for item in complete] == [3, 4])
    elif task == 'SC-D01':
        values = SortedSet([1, 2])
        failure = None
        try:
            values.add('x')
        except TypeError as error:
            failure = type(error).__name__
        result.update(error=failure, length=len(values), contains_x='x' in values, iteration=list(values))
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
