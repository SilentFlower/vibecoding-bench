"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import toolz
from collections import OrderedDict
business = False
try:
    calls = []
    original = {'a': {'b': 4}, 'other': []}
    result = toolz.update_in(original, iter(['a', 'b']), lambda value: calls.append(value) or value * 3, create=False, factory=OrderedDict)
    business = result['a']['b'] == 12 and calls == [4] and original['a']['b'] == 4
    business &= result['other'] is original['other'] and isinstance(result['a'], OrderedDict)
    result = toolz.update_in(original, ['a', 'c'], lambda value: 1 / 0, create=False)
    business &= result == original and result['a'] is original['a']
    failure = RuntimeError('callback')
    def fail(value):
        """回调自身错误。@param value 值。@return 不返回。"""
        raise failure
    try:
        toolz.update_in(original, ['a', 'b'], fail, create=False)
    except RuntimeError as error:
        business &= error is failure
    else:
        business = False
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(toolz.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
