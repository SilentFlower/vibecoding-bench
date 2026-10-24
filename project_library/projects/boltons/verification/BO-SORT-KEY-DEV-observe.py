"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import boltons
_candidate_source_root = root
business = False
try:
    from boltons.iterutils import untyped_sorted
    class Key:
        def __init__(self):
            self.calls=[]
        def __bool__(self):
            return False
        def __call__(self,value):
            self.calls.append(value)
            return value
    key=Key();values=['z',2,1,'a'];result=untyped_sorted(iter(values),key=key)
    business=result==[1,2,'a','z'] and key.calls==values

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(boltons.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
