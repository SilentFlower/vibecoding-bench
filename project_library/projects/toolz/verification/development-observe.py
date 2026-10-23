"""独立分批矩阵：任意标记文本、一次性流、身份比较和长度诊断。"""
import json
import os
from itertools import count, islice
from pathlib import Path
import toolz
from toolz import partition, partition_all


def observations():
    """与独立切片金标准比较，禁止用元素相等判断内部缺失。@return 业务事实。"""
    matrix = True
    for size in (1, 2, 4):
        for length in range(8):
            data = ['__no__pad__' if index % 2 == 0 else index for index in range(length)]
            wanted = [tuple(data[index:index + size]) for index in range(0, length, size)]
            for source in (data, iter(data)):
                try:
                    matrix &= list(partition_all(size, source)) == wanted
                except Exception:
                    matrix = False
    padding = list(partition(4, [8, 9], pad='__no__pad__')) == [(8, 9, '__no__pad__', '__no__pad__')]
    class CannotCompare:
        """不能被库擅自调用相等运算的数据对象。"""
        def __eq__(self, other):
            """拒绝相等比较。@param other 其他对象。@return 不返回。"""
            raise AssertionError('data equality must not be used')
    values = [CannotCompare() for _ in range(5)]
    batches = list(partition_all(3, iter(values)))
    identity = len(batches) == 2 and all(actual is expected for actual, expected in zip([item for group in batches for item in group], values))
    consumed = []
    def events():
        """记录实际读取，允许已有实现最多预读一批。@return 事件流。"""
        for value in count():
            consumed.append(value)
            yield value
    stream = partition_all(3, events())
    lazy = not consumed and next(stream) == (0, 1, 2) and len(consumed) <= 6
    return {'marker_matrix': matrix, 'explicit_padding': padding, 'identity_only': identity,
        'lazy_bounded_lookahead': lazy, 'ordinary_partition': list(partition(2, [0, 1, 2])) == [(0, 1)]}


print(json.dumps({'candidate_import': Path(toolz.__file__).resolve().is_relative_to(Path(os.environ['PROJECT_CANDIDATE_ROOT']) / 'library'), **observations()}))
