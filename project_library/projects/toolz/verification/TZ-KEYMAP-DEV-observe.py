"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import toolz
business = False
try:
    source = {'a': [1], 'A': [2], 'b': [3]}
    result = toolz.keymap(str.lower, source, collision='combine', combine=lambda left, right: left + right)
    business = result == {'a': [1, 2], 'b': [3]} and source['a'] == [1]
    failure = RuntimeError('resolver')
    def fail(left, right):
        """拒绝业务冲突。@param left 原值。@param right 后值。@return 不返回。"""
        raise failure
    try:
        toolz.keymap(str.lower, source, collision='combine', combine=fail)
    except RuntimeError as error:
        business &= error is failure
    else:
        business = False
    for policy in ('invalid', 'combine'):
        try:
            toolz.keymap(str.lower, {}, collision=policy)
        except (ValueError, TypeError):
            pass
        else:
            business = False
except TypeError:
    business = False

print(json.dumps({'candidate_import': Path(toolz.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
