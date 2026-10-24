"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import toolz
import itertools
business = toolz.tail(0, [5, 6]) == [] and toolz.tail(0, 'private') == ''
calls = []
def stream():
    """无限数据流，零项请求不可触发执行。@return 迭代器。"""
    while True:
        calls.append(1)
        yield len(calls)
class NoConsume:
    """一旦读取就失败的流。"""
    def __iter__(self):
        """读取被禁止。@return 不返回。"""
        raise AssertionError('零项不应读取')
try:
    business &= toolz.tail(0, NoConsume()) == ()
except AssertionError:
    business = False
source = iter([1, 2, 3])
business &= toolz.curried.tail(0)(source) == () and next(source, None) == 1
for item in [(1, 2), iter([1, 2])]:
    try:
        toolz.tail(-2, item)
    except ValueError:
        pass
    else:
        business = False
business &= toolz.tail(20, iter([1, 2])) == (1, 2) and toolz.last([4, 7]) == 7

print(json.dumps({'candidate_import': Path(toolz.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
