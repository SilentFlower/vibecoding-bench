"""用真实查询验证投影、默认、排序、结果归属及嵌套JSON比较。"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import jmespath
from jmespath import Options
from jmespath.exceptions import JMESPathTypeError, UnknownFunctionError
from jmespath.functions import Functions, signature


def observe(identifier: str) -> dict:
    """独立执行当前查询目标。@param identifier 稳定任务码。@return 实际事实。"""
    if identifier == 'JM-U01':
        data = {'records': [{'id': 'A'}, {}, {'id': None}, {'id': 0}, {'id': False}]}
        projection = jmespath.search('records[*].id', data)
        mapped = jmespath.search('map(&id, records)', data)
        return {'projection_drops_null_while_map_retains_positions':
            json.dumps(projection) == json.dumps(['A', 0, False])
            and json.dumps(mapped) == json.dumps(['A', None, None, 0, False])}
    if identifier == 'JM-C01':
        data = {'zero': 0, 'disabled': False, 'label': ''}
        values = jmespath.search('[zero || `99`, disabled || `99`, label || `99`]', data)
        nullable = jmespath.search('[not_null(zero, `99`), not_null(disabled, `99`), not_null(label, `99`)]', data)
        return {'truth_fallback_differs_from_null_fallback_and_key_presence':
            json.dumps(values) == json.dumps([0, 99, 99])
            and json.dumps(nullable) == json.dumps([0, False, ''])
            and jmespath.search('qty', {'qty': None}) is None and jmespath.search('qty', {}) is None
            and jmespath.search("contains(keys(@), 'qty')", {'qty': None}) is True
            and jmespath.search("contains(keys(@), 'qty')", {}) is False}
    if identifier == 'JM-C02':
        data = {'items': [{'id': 'A', 'price': '12'}, {'id': 'B', 'price': 2},
            {'id': 'C', 'price': 'bad'}, {'id': 'D', 'price': True}, {'id': 'E', 'price': None}]}
        original = deepcopy(data)
        try:
            jmespath.search('sort_by(items, &price)', data)
            typed_error = False
        except JMESPathTypeError:
            typed_error = True
        selected = jmespath.search('sort_by(items[?to_number(price) != `null`], &to_number(price))[].id', data)
        return {'numeric_sort_requires_explicit_conversion_and_invalid_policy':
            typed_error and selected == ['B', 'A'] and data == original
            and jmespath.search('to_number(`true`)', {}) is None}
    if identifier == 'JM-U02':
        compiled = jmespath.compile('`{"shared_tags":[]}`')
        first = compiled.search({})
        first['shared_tags'].append('caller-owned-edit')
        repeated = compiled.search({})
        cached = jmespath.search('`{"shared_tags":[]}`', {})
        safe = jmespath.compile('`{"owned_tags":[]}`')
        owned = deepcopy(safe.search({}))
        owned['owned_tags'].append('local-edit')
        return {'literal_results_can_alias_compiled_cache_and_need_owned_copies':
            first is repeated and repeated['shared_tags'] == ['caller-owned-edit']
            and cached['shared_tags'] == ['caller-owned-edit'] and safe.search({}) == {'owned_tags': []}}
    if identifier == 'JM-P01':
        class LocalFunctions(Functions):
            """只在显式选项内提供受信业务函数。"""

            @signature({'types': ['string']})
            def _func_store_key(self, value):
                """实现受信业务映射。@param value 合成仓库名。@return 规范化键。"""
                return value.lower()

        options = Options(custom_functions=LocalFunctions())
        result = jmespath.search('store_key(name)', {'name': 'WAREHOUSE-A'}, options=options)
        try:
            jmespath.search('store_key(name)', {'name': 'WAREHOUSE-A'})
            isolated = False
        except UnknownFunctionError:
            isolated = True
        try:
            jmespath.search('store_key(`1`)', {}, options=options)
            typed = False
        except JMESPathTypeError:
            typed = True
        return {'trusted_custom_function_uses_explicit_options_without_global_registration':
            result == 'warehouse-a' and isolated and typed
            and jmespath.search('length(`[1,2]`)', {}, options=options) == 2}
    if identifier == 'JM-M01':
        pairs = [([True], [1], False), ([False], [0], False),
            ({'x': [True]}, {'x': [1]}, False), ({'x': {'active': False}}, {'x': {'active': 0}}, False),
            ({'a': 1, 'b': [True]}, {'b': [True], 'a': 1.0}, True),
            ([1, 2], [2, 1], False), ([1], [1, 2], False), ({'x': None}, {}, False),
            (True, 1, False), (1, 1.0, True), (None, None, True)]
        checks = []
        for left, right, expected in pairs:
            for a, b in [(left, right), (right, left)]:
                value = {'a': a, 'b': b}
                before = json.dumps(value, sort_keys=True)
                checks.append(jmespath.search('a == b', value) is expected
                    and jmespath.search('a != b', value) is (not expected)
                    and json.dumps(value, sort_keys=True) == before)
        rows = {'items': [{'id': 'same', 'a': {'x': [True]}, 'b': {'x': [True]}},
            {'id': 'wrong-type', 'a': {'x': [True]}, 'b': {'x': [1]}},
            {'id': 'numeric', 'a': {'x': [1]}, 'b': {'x': [1.0]}}]}
        return {'nested_json_equality_preserves_boolean_types_and_numeric_controls':
            all(checks) and jmespath.search('items[?a==b].id', rows) == ['same', 'numeric']
            and jmespath.search('items[?a!=b].id', rows) == ['wrong-type']}
    raise ValueError('未知查询任务：' + identifier)


def main() -> None:
    """核真实候选导入并输出当前任务事实。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(jmespath.__file__).resolve() == root / 'library/jmespath/__init__.py',
        **observe(sys.argv[1])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
