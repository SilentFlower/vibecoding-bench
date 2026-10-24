"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import toolz
business = True
class Source:
    """不可使用len的可重复流。"""
    def __init__(self, values):
        """保存合成业务行。@param values 数据。@return None。"""
        self.values = values
        self.calls = 0
    def __iter__(self):
        """只允许一次读取。@return 迭代器。"""
        self.calls += 1
        if self.calls != 1:
            raise AssertionError('重复读取')
        return iter(self.values)
try:
    for values, expected in [(['x', 'y'], True), (['x', 'x', 'z'], False), ([], True)]:
        stream = Source(values)
        business &= toolz.isdistinct(stream) is expected and stream.calls == 1
    try:
        toolz.isdistinct(Source([[1], [2]]))
    except TypeError:
        pass
    else:
        business = False
except (TypeError, AssertionError):
    business = False

print(json.dumps({'candidate_import': Path(toolz.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
