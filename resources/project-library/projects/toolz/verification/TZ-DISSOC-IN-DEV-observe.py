"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import toolz
business = False
try:
    import tlz
    untouched = {'v': 9}
    original = {'x': {'y': {'z': 1}}, 'keep': untouched}
    result = toolz.dissoc_in(original, iter(['x', 'y', 'z']), prune=True)
    business = result == {'keep': untouched} and result['keep'] is untouched and original['x']['y']['z'] == 1
    business &= tlz.dissoc_in({'a': 1}, ['a']) == {}
    missing = toolz.dissoc_in(original, ['missing', 'leaf'])
    business &= missing == original and missing is not original and missing['x'] is original['x']
    business &= toolz.curried.dissoc_in({'x': {'y': None}})(['x', 'y']) == {'x': {}}
except (AttributeError, TypeError):
    business = False

print(json.dumps({'candidate_import': Path(toolz.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
