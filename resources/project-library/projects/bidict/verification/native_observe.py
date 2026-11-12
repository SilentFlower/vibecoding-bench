"""核双射冲突、实时反向视图和批量回滚的实际业务边界。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import bidict as package
from bidict import DROP_NEW, DROP_OLD, KeyDuplicationError, OnDup, ValueDuplicationError, bidict, frozenbidict


def main() -> None:
    """逐任务检查本次实际候选，不把映射回滚扩大为外部事务。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(package.__file__).resolve() == root / 'library/bidict/__init__.py'}
    task = argv[1]
    if task == 'BI-U01':
        mapping = bidict(a=1)
        mapping['a'] = 2
        strict, duplicate = False, False
        try:
            mapping.put('a', 3)
        except KeyDuplicationError:
            strict = True
        try:
            mapping['b'] = 2
        except ValueDuplicationError:
            duplicate = True
        result['assignment_and_put_have_distinct_duplicate_defaults'] = strict and duplicate and dict(mapping) == {'a': 2}
    elif task == 'BI-U02':
        mapping = bidict(a=1)
        inverse = mapping.inverse
        inverse[2] = 'b'
        del mapping['a']
        result['inverse_is_a_live_mutable_bijection_view'] = (
            inverse.inverse is mapping and dict(mapping) == {'b': 2} and dict(inverse) == {2: 'b'})
    elif task == 'BI-C01':
        mapping = bidict(a=1, b=2)
        mapping.put('a', 2, on_dup=OnDup(key=DROP_OLD, val=DROP_NEW))
        kept = dict(mapping) == {'a': 1, 'b': 2}
        mapping.forceput('a', 2)
        result['forceput_can_displace_two_associations_and_shrink_cardinality'] = (
            kept and dict(mapping) == {'a': 2} and dict(mapping.inverse) == {2: 'a'})
    elif task == 'BI-C02':
        mapping = bidict(a=1)
        snapshot, independent = frozenbidict(mapping), mapping.copy()
        mapping['b'] = 2
        result['copy_and_frozen_snapshot_are_independent_of_later_mapping_updates'] = (
            dict(snapshot) == dict(independent) == {'a': 1} and dict(mapping) == {'a': 1, 'b': 2}
            and hash(snapshot) == hash(frozenbidict(a=1)) and not hasattr(snapshot, '__setitem__'))
    elif task == 'BI-P01':
        mapping, events = bidict(a=1, b=2), []

        def rows():
            """记录生成器消费副作用，说明映射回滚范围。@return 逐项输入。"""
            for item in [('c', 3), ('d', 2)]:
                events.append(item)
                yield item

        source, raised = rows(), False
        try:
            mapping.putall(source)
        except ValueDuplicationError:
            raised = True
        result['bulk_rollback_does_not_undo_consumption_or_external_side_effects'] = (
            raised and dict(mapping) == {'a': 1, 'b': 2}
            and events == [('c', 3), ('d', 2)] and list(source) == [])
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
