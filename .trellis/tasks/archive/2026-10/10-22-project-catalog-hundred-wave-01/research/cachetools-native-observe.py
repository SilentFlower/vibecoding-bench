"""用真实文件、调用和容量副作用核验Cachetools场景，不匹配答案措辞。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import cachetools
from cachetools import Cache, TTLCache, cached, cachedmethod, keys


def file_observations() -> dict:
    """观察真实文件命中、TTL边界和解析错误重试。

    :return: 与候选算法独立的业务事实。
    """
    with tempfile.TemporaryDirectory(prefix='cachetools-config-') as directory:
        path = Path(directory) / 'settings.json'
        path.write_text(json.dumps({'商品': '咖啡', 'price': 35}), encoding='utf-8')
        clock, reads = [0.0], []
        cache = TTLCache(4, 5, timer=lambda: clock[0])

        @cached(cache)
        def load(filename: str) -> dict:
            """读取实际配置文件。@param filename 临时路径。@return JSON对象。"""
            reads.append(filename)
            return json.loads(Path(filename).read_text(encoding='utf-8'))

        first = load(str(path))
        second = load(str(path))
        path.write_text(json.dumps({'商品': '咖啡', 'price': 40}), encoding='utf-8')
        clock[0] = 4.999
        before_expiry = load(str(path))
        clock[0] = 5.0
        at_expiry = load(str(path))
        normal = (first == second == before_expiry == {'商品': '咖啡', 'price': 35}
            and at_expiry == {'商品': '咖啡', 'price': 40} and len(reads) == 2)
        bad = Path(directory) / 'bad.json'
        bad.write_text('{bad-json', encoding='utf-8')
        rejected = False
        try:
            load(str(bad))
        except json.JSONDecodeError:
            rejected = True
        bad.write_text(json.dumps({'valid': True}), encoding='utf-8')
        recovered = load(str(bad))
        return {'file_hit_and_expiry': normal, 'file_change_waits_for_ttl': normal,
            'invalid_json_not_cached': rejected and recovered == {'valid': True}
                and reads.count(str(bad)) == 2}


def key_observations() -> dict:
    """区分调用归一化、类型区分和业务方法命名空间。

    :return: 实际原生缓存结果。
    """
    calls, normalized_calls = [], []

    @cached({}, info=True)
    def quote(quantity=1):
        """记录实际报价次数。@param quantity 数量。@return 数量。"""
        calls.append(quantity)
        return quantity

    @cached({}, key=lambda quantity=1: keys.hashkey(quantity), info=True)
    def normalized_quote(quantity=1):
        """用已有key参数归一化调用。@param quantity 数量。@return 数量。"""
        normalized_calls.append(quantity)
        return quantity

    for function in (quote, normalized_quote):
        function()
        function(1)
        function(quantity=1)

    class Prices:
        """用一个真实缓存演示两个业务方法的键边界。"""

        def __init__(self) -> None:
            """创建实例私有共享缓存。@return None。"""
            self.cache = {}

        @cachedmethod(lambda owner: owner.cache)
        def retail(self, sku: str) -> int:
            """返回零售价。@param sku 合成商品。@return 金额。"""
            return 100

        @cachedmethod(lambda owner: owner.cache)
        def wholesale(self, sku: str) -> int:
            """返回批发价。@param sku 合成商品。@return 金额。"""
            return 90

    class NamespacedPrices:
        """以现有key接口隔离两个业务方法。"""

        def __init__(self) -> None:
            """创建实例缓存。@return None。"""
            self.cache = {}

        @cachedmethod(lambda owner: owner.cache, key=lambda owner, *args, **kwargs: keys.hashkey('retail', *args, **kwargs))
        def retail(self, sku: str) -> int:
            """返回隔离零售价。@param sku 合成商品。@return 金额。"""
            return 100

        @cachedmethod(lambda owner: owner.cache, key=lambda owner, *args, **kwargs: keys.hashkey('wholesale', *args, **kwargs))
        def wholesale(self, sku: str) -> int:
            """返回隔离批发价。@param sku 合成商品。@return 金额。"""
            return 90

    ordinary, namespaced = Prices(), NamespacedPrices()
    return {'raw_call_forms_are_distinct': calls == [1, 1, 1] and quote.cache_info().misses == 3,
        'custom_key_normalizes': normalized_calls == [1] and normalized_quote.cache_info().hits == 2,
        'typed_keys_distinguish': keys.hashkey(1) == keys.hashkey(1.0) and keys.typedkey(1) != keys.typedkey(1.0),
        'shared_cache_collision': [ordinary.retail('coffee'), ordinary.wholesale('coffee')] == [100, 100],
        'namespaced_methods': [namespaced.retail('coffee'), namespaced.wholesale('coffee')] == [100, 90]}


def type_error(function) -> bool:
    """只将实际TypeError视为调用边界拒绝。

    :param function: 受控调用。
    :return: 是否按调用契约拒绝。
    """
    try:
        function()
    except TypeError:
        return True
    return False


def receiver_observations() -> dict:
    """直接比较位置、关键字、实例、非标准receiver名和非法调用。

    :return: 不依赖补丁实现方式的调用矩阵。
    """
    class Catalog:
        """拥有独立价格和命中统计的合成业务对象。"""

        def __init__(self, base=1) -> None:
            """初始化价格倍率和缓存。@param base 倍率。@return None。"""
            self.cache = {}
            self.base = base

        @cachedmethod(lambda owner: owner.cache, info=True)
        def quote(self, sku: str) -> int:
            """计算实际报价。@param sku 商品。@return 金额。"""
            return {'coffee': 10, 'tea': 15}[sku] * self.base

    class NamedReceiver:
        """receiver名称无需固定为self。"""

        def __init__(self) -> None:
            """初始化独立缓存。@return None。"""
            self.cache = {}

        @cachedmethod(lambda instance: instance.cache)
        def quote(owner, sku: str) -> str:
            """返回原始业务参数。@param owner 实例。@param sku 商品。@return 商品。"""
            return sku

    class PositionalReceiver:
        """原函数的位置专用receiver不应被补丁放宽。"""

        def __init__(self) -> None:
            """创建缓存。@return None。"""
            self.cache = {}

        @cachedmethod(lambda owner: owner.cache)
        def quote(self, /, sku: str) -> str:
            """保留位置专用调用。@param sku 商品。@return 商品。"""
            return sku

    catalog = Catalog()
    positional = Catalog.quote(catalog, sku='coffee')
    bound = catalog.quote(sku='coffee')
    rejected_before_fix = type_error(lambda: Catalog.quote(self=catalog, sku='coffee'))
    try:
        keyword = Catalog.quote(self=catalog, sku='coffee')
    except TypeError:
        keyword = None
    named = NamedReceiver()
    try:
        named_value = NamedReceiver.quote(owner=named, sku='tea')
    except TypeError:
        named_value = None
    other = Catalog(base=3)
    position_only = PositionalReceiver()
    return {'positional_bound_controls': positional == bound == 10,
        'original_keyword_receiver_rejected': rejected_before_fix,
        'keyword_receiver_equivalent': keyword == positional == 10,
        'custom_receiver_name': named_value == 'tea',
        'missing_receiver_rejected': type_error(lambda: Catalog.quote(sku='coffee')),
        'duplicate_receiver_rejected': type_error(lambda: Catalog.quote(catalog, self=catalog, sku='coffee')),
        'positional_only_preserved': PositionalReceiver.quote(position_only, sku='tea') == 'tea'
            and type_error(lambda: PositionalReceiver.quote(self=position_only, sku='tea')),
        'instance_isolation': other.quote(sku='coffee') == 30 and catalog.quote(sku='coffee') == 10,
        'cache_info_preserved': catalog.quote.cache_info().misses == 1
            and catalog.quote.cache_info().hits == (4 if keyword is not None else 2)}


def size_observations() -> dict:
    """观察可变值在插入和重新赋值时的真实容量记账。

    :return: 账本与超限拒绝事实。
    """
    cache = Cache(5, getsizeof=len)
    rows = ['coffee']
    cache['rows'] = rows
    rows.append('tea')
    unchanged = cache.currsize == 1 and len(cache['rows']) == 2
    cache['rows'] = rows
    reinserted = cache.currsize == 2
    try:
        cache['huge'] = list(range(6))
    except ValueError:
        oversize = 'huge' not in cache and cache.currsize == 2
    else:
        oversize = False
    return {'insertion_time_size': unchanged, 'explicit_reinsert_updates_size': reinserted,
        'oversize_rejected': oversize}


def main() -> None:
    """按冻结任务输出实际业务观察，异常不伪装成功。

    :return: None。
    """
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(root / 'library/src/cachetools')}
    if task in ('CT-U01', 'CT-C01', 'CT-P01'):
        observations = file_observations()
    elif task in ('CT-C02', 'CT-U02'):
        observations = key_observations()
    elif task in ('CT-D02', 'CT-M01'):
        observations = receiver_observations()
    elif task == 'CT-C03':
        observations = size_observations()
    else:
        raise ValueError('没有该任务的冻结原生业务')
    fields = {
        'CT-U01': ('file_hit_and_expiry',), 'CT-C01': ('file_change_waits_for_ttl',),
        'CT-P01': ('file_hit_and_expiry', 'invalid_json_not_cached'),
        'CT-C02': ('shared_cache_collision', 'namespaced_methods'),
        'CT-U02': ('raw_call_forms_are_distinct', 'custom_key_normalizes', 'typed_keys_distinguish'),
        'CT-D02': ('positional_bound_controls', 'original_keyword_receiver_rejected'),
        'CT-M01': ('positional_bound_controls', 'keyword_receiver_equivalent', 'custom_receiver_name',
            'missing_receiver_rejected', 'duplicate_receiver_rejected', 'positional_only_preserved',
            'instance_isolation', 'cache_info_preserved'),
        'CT-C03': ('insertion_time_size', 'explicit_reinsert_updates_size', 'oversize_rejected')}
    result.update({field: observations[field] for field in fields[task]})
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
