"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import box
business = False
try:
    value = box.Box({'x': [1], 'm': {'v': 2}, 'z': 3})
    child = value.m
    value.rename_key('m', 'new-key')
    business = list(value) == ['x', 'new-key', 'z'] and value.new_key is child
    before = value.to_dict()
    for old, new in [('absent', 'u'), ('x', 'z')]:
        try:
            value.rename_key(old, new)
        except box.BoxError:
            pass
        else:
            business = False
        business &= value.to_dict() == before
    business &= value.rename_key('x', 'x') is value
except AttributeError:
    business = False

print(json.dumps({'candidate_import': Path(box.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
