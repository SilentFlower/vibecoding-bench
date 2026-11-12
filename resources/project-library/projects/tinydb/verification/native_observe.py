"""在隔离容器观察 TinyDB 候选的独立业务行为并输出固定 JSON。"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Callable


def observe(operation: Callable[[], object]) -> object:
    """保留失败观察，避免单项异常掩盖其他反例。@param operation 业务调用。@return 真实结果或异常类型。"""
    try:
        return operation()
    except Exception as error:
        return {'error_type': type(error).__name__}


def database(storage: str, path: Path, **kwargs):
    """为每例构造独立数据库。@param storage 存储类型。@param path 临时文件。@param kwargs 既有配置。@return TinyDB 实例。"""
    from tinydb import TinyDB
    from tinydb.storages import MemoryStorage

    return TinyDB(storage=MemoryStorage, **kwargs) if storage == 'memory' else TinyDB(path, **kwargs)


def fragment_baseline() -> dict:
    """观察原版业务字段的顺序相关缓存污染。@return 两存储实际 ID 对照。"""
    from tinydb import Query

    result = {}
    for storage in ('memory', 'json'):
        with TemporaryDirectory(prefix='td-fragment-baseline-') as directory:
            with database(storage, Path(directory) / 'data.json') as db:
                db.insert_multiple([
                    {'sku': 'A', 'billing': {'city': 'Oslo'}, 'shipping': {'city': 'Lima'}},
                    {'sku': 'B', 'billing': {'city': 'Lima'}, 'shipping': {'city': 'Oslo'}},
                ])
                billing = Query().billing.fragment({'city': 'Oslo'})
                shipping = Query().shipping.fragment({'city': 'Oslo'})
                ids = lambda documents: [document.doc_id for document in documents]
                observed = {'billing_first': ids(db.search(billing)),
                    'shipping_after': ids(db.search(shipping)),
                    'shipping_direct': ids([doc for doc in db.all() if shipping(doc)])}
                db.clear_cache()
                observed['uncached_shipping'] = ids(db.search(shipping))
                db.clear_cache()
                observed['reversed_first'] = ids(db.search(shipping))
                observed['billing_after_reverse'] = ids(db.search(billing))
                result[storage] = observed
    return result


def fragment_case(storage: str, reverse: bool, deep: bool = False) -> bool:
    """核对完整路径和命中缓存，使用与公开复现不同的字段。@param storage 后端。@param reverse 顺序。@param deep 深路径。@return 是否正确。"""
    from tinydb import Query

    with TemporaryDirectory(prefix='td-fragment-') as directory:
        with database(storage, Path(directory) / 'data.json') as db:
            left, right = ('invoice', 'dispatch') if deep else ('origin', 'destination')
            docs = [{left: {'zone': 'north'}, right: {'zone': 'south'}, 'active': True},
                {left: {'zone': 'south'}, right: {'zone': 'north'}, 'active': True},
                {left: {'zone': 'west'}, right: {}, 'active': False}, {'active': False}]
            if deep:
                docs = [{'region': doc} for doc in docs]
            db.insert_multiple(docs)
            query = Query().region if deep else Query()
            queries = [(query[left].fragment({'zone': 'north'}), [1]),
                (query[right].fragment({'zone': 'north'}), [2])]
            if reverse:
                queries.reverse()
            for condition, expected in queries:
                if not condition.is_cacheable():
                    return False
                for _ in range(2):
                    if [doc.doc_id for doc in db.search(condition)] != expected:
                        return False
            # 必须实际保存两个正常缓存条目；恒禁缓存不能满足性能兼容边界。
            return len(db._query_cache) == 2


def fragment_compatibility() -> dict:
    """独立验证根片段、组合、缺失、值区别及 map 边界。@return 逐项观察。"""
    from tinydb import Query
    from tinydb.storages import MemoryStorage
    from tinydb import TinyDB

    def root_and_empty() -> bool:
        """核对根级、空片段和缺失路径。@return 是否符合现有行为。"""
        with TinyDB(storage=MemoryStorage) as db:
            db.insert_multiple([{'rank': 7, 'meta': {'x': 1}}, {'rank': 8}, {}])
            return ([doc.doc_id for doc in db.search(Query().fragment({'rank': 7}))] == [1]
                and len(db.search(Query().fragment({}))) == 3
                and [doc.doc_id for doc in db.search(Query().meta.fragment({}))] == [1]
                and db.search(Query().missing.fragment({'x': 1})) == [])

    def composition() -> bool:
        """验证与、或和取反没有发生缓存等价错误。@return 是否正确。"""
        with TinyDB(storage=MemoryStorage) as db:
            db.insert_multiple([{'a': {'x': 1}, 'b': {'x': 0}, 'ok': True},
                {'a': {'x': 0}, 'b': {'x': 1}, 'ok': True},
                {'a': {'x': 1}, 'b': {'x': 1}, 'ok': False}])
            a = Query().a.fragment({'x': 1})
            b = Query().b.fragment({'x': 1})
            good = Query().ok == True
            return ([d.doc_id for d in db.search(a & good)] == [1]
                and [d.doc_id for d in db.search(b & good)] == [2]
                and [d.doc_id for d in db.search(a | b)] == [1, 2, 3]
                and [d.doc_id for d in db.search(~a)] == [2])

    def values_and_unicode() -> bool:
        """核对同路径不同值与非示例路径。@return 是否分离。"""
        with TinyDB(storage=MemoryStorage) as db:
            db.insert_multiple([{'地域': {'值': [1, 2]}}, {'地域': {'值': [2, 1]}}])
            first = Query()['地域'].fragment({'值': [1, 2]})
            second = Query()['地域'].fragment({'值': [2, 1]})
            return [d.doc_id for d in db.search(first)] == [1] and [d.doc_id for d in db.search(second)] == [2]

    def map_remains_dynamic() -> bool:
        """让同一个 callable 改变目标，确认查询不会被错误缓存。@return 是否每次重算。"""
        with TinyDB(storage=MemoryStorage) as db:
            db.insert_multiple([{'a': {'x': 1}, 'b': {'x': 0}}, {'a': {'x': 0}, 'b': {'x': 1}}])
            state = {'field': 'a'}
            condition = Query().map(lambda document: document[state['field']]).fragment({'x': 1})
            if condition.is_cacheable() or [d.doc_id for d in db.search(condition)] != [1]:
                return False
            state['field'] = 'b'
            return [d.doc_id for d in db.search(condition)] == [2] and len(db._query_cache) == 0

    def unhashable_values() -> bool:
        """保留不能 freeze 的业务值降级为不可缓存的行为。@return 是否正常查值。"""
        class Value:
            """模拟可比较但不可哈希的业务值。"""
            __hash__ = None

            def __eq__(self, other) -> bool:
                """比较同类型值。@param other 对照对象。@return 是否相等。"""
                return isinstance(other, Value)

        value = Value()
        with TinyDB(storage=MemoryStorage) as db:
            db.insert({'box': {'value': value}})
            condition = Query().box.fragment({'value': value})
            return not condition.is_cacheable() and len(db.search(condition)) == 1 and len(db._query_cache) == 0

    return {name: observe(operation) for name, operation in {'root_empty_missing': root_and_empty,
        'boolean_composition': composition, 'fragment_values_unicode': values_and_unicode,
        'map_remains_uncacheable': map_remains_dynamic, 'unhashable_fallback': unhashable_values}.items()}


def fragment_observations() -> dict:
    """执行真实路径和存储矩阵。@return 结果，不以哈希数值不同代替行为。"""
    result = {}
    for storage in ('memory', 'json'):
        for reverse in (False, True):
            for deep in (False, True):
                key = f'{storage}_{"reverse" if reverse else "forward"}_{"deep" if deep else "flat"}'
                result[key] = observe(lambda: fragment_case(storage, reverse, deep))
    return {**result, **fragment_compatibility()}


def batch_baseline() -> dict:
    """以同业务条件比较原版列表和生成器。@return 两存储真实结果。"""
    from tinydb import Query

    result = {}
    for storage in ('memory', 'json'):
        observed = {}
        for mode in ('list', 'generator'):
            with TemporaryDirectory(prefix='td-batch-baseline-') as directory:
                with database(storage, Path(directory) / 'data.json') as db:
                    db.insert_multiple([{'sku': 'A', 'qty': 1}, {'sku': 'B', 'qty': 2}])
                    rules = [({'done': True}, Query().qty > 0)]
                    updates = rules if mode == 'list' else (rule for rule in rules)
                    updated = db.update_multiple(updates)
                    observed[mode] = {'ids': updated, 'done': [doc.get('done', False) for doc in db.all()]}
        result[storage] = observed
    return result


def batch_case(storage: str, mode: str) -> bool:
    """验证规则顺序、返回重复 ID 和原地回调。@param storage 后端。@param mode 可迭代类型。@return 是否相等。"""
    from tinydb import Query
    from tinydb.operations import increment

    with TemporaryDirectory(prefix='td-batch-') as directory:
        path = Path(directory) / 'data.json'
        with database(storage, path) as db:
            db.insert_multiple([{'sku': 'X', 'qty': 0}, {'sku': 'Y', 'qty': 0}, {'sku': 'Z', 'qty': 8}])
            rules = [(increment('qty'), Query().qty == 0), ({'stage': 'ready'}, Query().qty == 1)]
            source = {'list': lambda: rules, 'tuple': lambda: tuple(rules),
                'iterator': lambda: iter(rules), 'generator': lambda: (rule for rule in rules)}[mode]()
            updated = db.update_multiple(source)
            expected = [{'sku': 'X', 'qty': 1, 'stage': 'ready'},
                {'sku': 'Y', 'qty': 1, 'stage': 'ready'}, {'sku': 'Z', 'qty': 8}]
            if updated != [1, 1, 2, 2] or db.all() != expected:
                return False
            db.clear_cache()
            if [doc.doc_id for doc in db.search(Query().stage == 'ready')] != [1, 2]:
                return False
        if storage == 'json':
            with database(storage, path) as reopened:
                return reopened.all() == expected
        return True


def enumeration_failure(storage: str) -> bool:
    """部分枚举异常前不可应用规则，特别覆盖内存存储引用。@param storage 后端。@return 文档和磁盘是否保持。"""
    from tinydb import Query

    with TemporaryDirectory(prefix='td-enumeration-') as directory:
        path = Path(directory) / 'data.json'
        with database(storage, path) as db:
            db.insert_multiple([{'sku': 'X', 'qty': 3}, {'sku': 'Y', 'qty': 5}])
            before = deepcopy(db.all())
            previous_bytes = path.read_bytes() if storage == 'json' else None

            def broken_rules():
                """在已有一条规则后模拟配置加载失败。@return 先产规则后抛出异常。"""
                yield ({'touched': True}, Query().qty > 0)
                raise ValueError('rule loader failed')

            try:
                db.update_multiple(broken_rules())
            except ValueError as error:
                if str(error) != 'rule loader failed':
                    return False
            else:
                return False
            return db.all() == before and (storage != 'json' or path.read_bytes() == previous_bytes)


def batch_boundaries(storage: str) -> bool:
    """覆盖空表、空规则、无命中、单文档与顺序反例。@param storage 后端。@return 是否兼容。"""
    from tinydb import Query
    from tinydb.operations import increment

    with TemporaryDirectory(prefix='td-batch-boundaries-') as directory:
        with database(storage, Path(directory) / 'data.json') as db:
            if db.update_multiple(iter([({'x': 1}, Query().qty > 0)])) != []:
                return False
            db.insert({'sku': 'X', 'qty': 0})
            before = deepcopy(db.all())
            if db.update_multiple(iter([])) != [] or db.all() != before:
                return False
            if db.update_multiple(iter([({'x': 1}, Query().qty < 0)])) != [] or db.all() != before:
                return False
            rules = [({'stage': 'ready'}, Query().qty == 1), (increment('qty'), Query().qty == 0)]
            return db.update_multiple(iter(rules)) == [1] and db.all() == [{'sku': 'X', 'qty': 1}]


def batch_observations() -> dict:
    """运行有限规则矩阵及枚举失败反例。@return 逐项观察。"""
    result = {}
    for storage in ('memory', 'json'):
        for mode in ('list', 'tuple', 'iterator', 'generator'):
            result[f'{storage}_{mode}'] = observe(lambda: batch_case(storage, mode))
        result[f'{storage}_enumeration_failure'] = observe(lambda: enumeration_failure(storage))
        result[f'{storage}_boundary_cases'] = observe(lambda: batch_boundaries(storage))
    return result


def consult_observations(root: Path, answer_file: Path | None) -> dict:
    """只执行唯一完整回答程序，随后独立重开核对持久结果。@param root 候选根。@param answer_file 封存回答。@return 观察。"""
    from tinydb import TinyDB
    from tinydb import Query

    if answer_file is None or not answer_file.is_file() or answer_file.stat().st_size > 262144:
        return {'error': 'answer_missing_or_large'}
    answer = answer_file.read_text(encoding='utf-8')
    programs = re.findall(r'```[ \t]*(?:python|py)[ \t]*\n(.*?)```', answer, flags=re.DOTALL)
    if len(programs) != 1 or len(programs[0].encode()) > 65536:
        return {'unique_program': False, 'program_count': len(programs)}
    with TemporaryDirectory(prefix='td-consult-') as directory:
        business = Path(directory)
        script, path = business / 'example.py', business / 'orders.json'
        script.write_text(programs[0], encoding='utf-8')
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(root / 'library')
        output, errors = business / 'stdout.txt', business / 'stderr.txt'
        try:
            with output.open('wb') as stdout, errors.open('wb') as stderr:
                completed = subprocess.run([sys.executable, '-B', str(script), str(path)],
                    cwd=business, env=environment, stdout=stdout, stderr=stderr, timeout=8, check=False)
        except subprocess.TimeoutExpired:
            return {'error': 'example_timeout'}
        if output.stat().st_size > 1048576 or errors.stat().st_size > 1048576:
            return {'error': 'example_output_large'}
        if completed.returncode or not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
            return {'returncode': completed.returncode, 'database_exists': path.is_file()}
        with TinyDB(path) as db:
            orders = db.table('orders')
            a, b = orders.get(Query().sku == 'A'), orders.get(Query().sku == 'B')
            values_ok = a == {'sku': 'A', 'qty': 2} and b == {'sku': 'B', 'qty': 2}
            count_ok = len(orders) == 2 and len(db) == 0
        printed = []
        for line in output.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                printed.append(json.loads(line))
            except ValueError:
                continue
        return {'unique_program': True, 'returncode': completed.returncode,
            'persisted_values': values_ok, 'named_table_only': count_ok,
            'queried_order_printed': {'sku': 'A', 'qty': 2} in printed}


def main() -> None:
    """读取固定模式并核实候选实际导入路径。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['fragment', 'batch', 'fragment-baseline', 'batch-baseline', 'consult'])
    parser.add_argument('--candidate-root', type=Path, default=Path(os.environ.get('PROJECT_CANDIDATE_ROOT', '/work/project')))
    parser.add_argument('--answer-file', type=Path, default=Path(os.environ['PROJECT_ANSWER_FILE']) if os.environ.get('PROJECT_ANSWER_FILE') else None)
    options = parser.parse_args()
    root = options.candidate_root.resolve()
    sys.path.insert(0, str(root / 'library'))
    import tinydb

    imported = Path(tinydb.__file__).resolve().is_relative_to((root / 'library').resolve())
    operations = {'fragment': fragment_observations, 'batch': batch_observations,
        'fragment-baseline': fragment_baseline, 'batch-baseline': batch_baseline,
        'consult': lambda: consult_observations(root, options.answer_file)}
    result = operations[options.mode]()
    print(json.dumps({'candidate_import': imported, **result}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
