"""观察持久映射及记录的真实更新和验收边界。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import pyrsistent
from pyrsistent import InvariantException, PClass, PTypeError, field, freeze, pmap


class Range(PClass):
    """声明合成区间以及跨字段约束；无真实业务数据。"""
    low = field(type=int, mandatory=True)
    high = field(type=int, mandatory=True)
    __invariant__ = lambda self: (self.low <= self.high, 'low must not exceed high')


class Item(PClass):
    """声明合成数量记录，用于核类型与显式转换。"""
    count = field(type=int, mandatory=True)


class ConvertedItem(PClass):
    """仅在明确声明的工厂中转换数量。"""
    count = field(type=int, mandatory=True, factory=int)


def main() -> None:
    """本业务入口只验映射和记录；C向量另由完整原生基线验证。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(pyrsistent.__file__).resolve() == root / 'library/pyrsistent/__init__.py'}
    task = argv[1]
    if task == 'PS-U01':
        values = ['tea']
        shallow = pmap({'items': values})
        deep = freeze({'items': values})
        values.append('book')
        result['persistent_outer_map_does_not_freeze_mutable_values'] = (
            shallow['items'] is values and shallow['items'] == ['tea', 'book']
            and list(deep['items']) == ['tea'])
    elif task == 'PS-U02':
        original = pmap({'tea': 1})
        staging = original.evolver()
        staging['tea'] = 2
        first = staging.persistent()
        staging['tea'] = 3
        second = staging.persistent()
        result['evolver_is_mutable_and_published_snapshots_are_independent'] = (
            original == {'tea': 1} and first == {'tea': 2} and second == {'tea': 3}
            and staging['tea'] == 3 and first is not second)
    elif task == 'PS-C01':
        rejected = False
        try:
            Item(count='3')
        except PTypeError:
            rejected = True
        result['field_type_checks_do_not_imply_conversion'] = (
            rejected and ConvertedItem(count='3').count == 3 and Item(count=3).count == 3)
    elif task == 'PS-C02':
        extra = {'count': 3, 'currency': 'EUR'}
        rejected = False
        try:
            Item.create(extra)
        except AttributeError:
            rejected = True
        result['ignoring_extra_fields_is_explicit_and_drops_unmodeled_input'] = (
            rejected and Item.create(extra, ignore_extra=True).serialize() == {'count': 3}
            and extra == {'count': 3, 'currency': 'EUR'})
    elif task == 'PS-P01':
        original = Range(low=0, high=5)
        rejected = False
        try:
            original.set(low=10)
        except InvariantException:
            rejected = True
        combined = original.set(low=10, high=20)
        staging = original.evolver()
        staging.low = 10
        staged_rejected = False
        try:
            staging.persistent()
        except InvariantException:
            staged_rejected = True
        staging.high = 20
        published = staging.persistent()
        result['cross_field_invariants_validate_complete_published_records'] = (
            rejected and staged_rejected and combined == published
            and (published.low, published.high) == (10, 20)
            and (original.low, original.high) == (0, 5))
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
