"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import box
business = False
try:
    value = box.Box({'a': {'rows': [{'v': 3}, {'v': 4}]}, 2: 'int', '2': 'str'}, default_box=True)
    business = value.get_path([2]) == 'int' and value.get_path(['2']) == 'str'
    value.set_path(['a', 'rows', -1, 'v'], 9)
    business &= value.get_path(['a', 'rows', 1, 'v']) == 9
    value.delete_path(['a', 'rows', 0])
    business &= len(value.a.rows) == 1
    snapshot = value.to_dict()
    try:
        value.set_path(['absent', 'child'], 1)
    except KeyError:
        pass
    else:
        business = False
    business &= value.to_dict() == snapshot
    try:
        value.get_path('a.rows')
    except TypeError:
        pass
    else:
        business = False
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(box.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
