"""直接观察重复报告、有限批次、嵌套清理和JSONL消费。"""
from __future__ import annotations

import json
import os
import sys
from io import BytesIO
from pathlib import Path

import boltons
from boltons.iterutils import PathAccessError, chunked_iter, get_path, redundant, remap, unique
from boltons.jsonutils import JSONLIterator


VALUES = ['A', 'a', 'a', 'B', 'b']


def rejects(function, exception: type[Exception]) -> bool:
    """只接受约定异常类型。@param function 调用。@param exception 异常类。@return 是否拒绝。"""
    try:
        function()
    except exception:
        return True
    return False


def duplication_observations() -> dict:
    """核原始业务值、分组及falsey callable的真实执行。@return 重复项矩阵。"""
    class FalseKey:
        """合法归一化函数不因自身真值改变能力。"""

        def __call__(self, value):
            """取大小写归一化键。@param value 原值。@return 业务键。"""
            return value.lower()

        def __bool__(self):
            """模拟合法falsey对象。@return False。"""
            return False

    class EmptyKey:
        """仅通过长度体现falsey的另一种callable。"""

        def __call__(self, value):
            """对实际记录取键。@param value 记录。@return 小写编码。"""
            return value['code'].lower()

        def __len__(self):
            """模拟零长度callable。@return 0。"""
            return 0

    ordinary = redundant(VALUES, key=str.lower)
    falsey = redundant(VALUES, key=FalseKey())
    grouped = redundant(VALUES, key=FalseKey(), groups=True)
    rows = [{'code': 'A'}, {'code': 'a'}]
    try:
        records = redundant(rows, key=EmptyKey())
    except TypeError:
        records = None

    def bad_key(value):
        """保留应用key失败。@param value 记录。@return 不返回。"""
        raise ValueError('归一化失败')

    return {'ordinary_duplicate_semantics': unique(VALUES, key=str.lower) == ['A', 'B']
            and ordinary == ['a', 'b']
            and redundant(VALUES, key=str.lower, groups=True) == [['A', 'a', 'a'], ['B', 'b']],
        'original_falsey_key_ignored': falsey != ordinary,
        'falsey_callable_respected': falsey == ordinary == ['a', 'b'],
        'falsey_group_mode_preserved': grouped == [['A', 'a', 'a'], ['B', 'b']],
        'zero_length_callable_handles_records': records == [rows[1]],
        'none_default_preserved': redundant([1, 1, 2, 2, 2]) == [1, 2],
        'invalid_and_key_errors_preserved': rejects(lambda: redundant(VALUES, key=0), TypeError)
            and rejects(lambda: redundant(VALUES, key=bad_key), ValueError)}


def batch_observations() -> dict:
    """核实际消费量与显式None填充，不做全源预缓冲。@return 批次事实。"""
    consumed = []

    def records():
        """记录源消费。@return 合成记录生成器。"""
        for value in range(5):
            consumed.append(value)
            yield value

    batches = chunked_iter(records(), 2)
    before = list(consumed)
    first = next(batches)
    after_first = list(consumed)
    remaining = list(batches)
    return {'chunk_consumption_is_incremental': before == [] and first == [0, 1]
            and after_first == [0, 1] and remaining == [[2, 3], [4]],
        'explicit_none_fill_is_distinct': list(chunked_iter(range(5), 2, fill=None)) == [
            [0, 1], [2, 3], [4, None]],
        'nonpositive_batch_size_rejected': rejects(lambda: list(chunked_iter([1], 0)), ValueError)}


def nested_observations() -> dict:
    """区分None清理、其他falsy值和路径缺失。@return 嵌套数据事实。"""
    record = {'line': {'empty': None, 'count': 0, 'enabled': False, 'label': ''}, 'notes': [None, 'coffee']}
    before = json.loads(json.dumps(record))
    cleaned = remap(record, visit=lambda path, key, value: value is not None)
    missing = object()
    return {'only_none_removed_recursively': cleaned == {'line': {'count': 0, 'enabled': False, 'label': ''},
            'notes': ['coffee']} and record == before and cleaned is not record,
        'missing_path_distinguished_from_none': get_path(record, ('line', 'empty'), default=missing) is None
            and get_path(record, ('line', 'absent'), default=missing) is missing,
        'path_error_remains_explicit': rejects(lambda: get_path(record, ('line', 'absent')), PathAccessError)}


def jsonl_observations() -> dict:
    """由真实字节源核坏行策略和反向顺序。@return 实际记录事实。"""
    raw = b'{"id":1}\n\nbad\n{"id":2}\n'
    strict = JSONLIterator(BytesIO(raw))
    first = next(strict)
    failed = rejects(lambda: next(strict), json.JSONDecodeError)
    skipped = list(JSONLIterator(BytesIO(raw), ignore_errors=True))
    reverse = list(JSONLIterator(BytesIO(raw), ignore_errors=True, reverse=True))
    return {'strict_jsonl_error_observed': first == {'id': 1} and failed,
        'skip_and_reverse_order_observed': skipped == [{'id': 1}, {'id': 2}]
            and reverse == [{'id': 2}, {'id': 1}]}


def main() -> None:
    """输出当前任务冻结的事实，不读取答案文本。@return None。"""
    task = sys.argv[1]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    selected = {'BO-U01': ('ordinary_duplicate_semantics',), 'BO-C01': ('ordinary_duplicate_semantics',),
        'BO-D01': ('original_falsey_key_ignored', 'ordinary_duplicate_semantics'),
        'BO-M01': ('falsey_callable_respected', 'falsey_group_mode_preserved',
            'zero_length_callable_handles_records', 'none_default_preserved', 'invalid_and_key_errors_preserved'),
        'BO-U02': ('chunk_consumption_is_incremental', 'explicit_none_fill_is_distinct'),
        'BO-P01': ('chunk_consumption_is_incremental', 'explicit_none_fill_is_distinct', 'nonpositive_batch_size_rejected'),
        'BO-U03': ('only_none_removed_recursively',),
        'BO-C02': ('missing_path_distinguished_from_none', 'path_error_remains_explicit'),
        'BO-U04': ('strict_jsonl_error_observed', 'skip_and_reverse_order_observed'),
        'BO-P02': ('strict_jsonl_error_observed', 'skip_and_reverse_order_observed')}
    if task in ('BO-U01', 'BO-C01', 'BO-D01', 'BO-M01'):
        facts = duplication_observations()
    elif task in ('BO-U02', 'BO-P01'):
        facts = batch_observations()
    elif task in ('BO-U03', 'BO-C02'):
        facts = nested_observations()
    else:
        facts = jsonl_observations()
    print(json.dumps({'candidate_import': Path(boltons.__file__).resolve() == root / 'library/boltons/__init__.py',
        **{field: facts[field] for field in selected[task]}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
