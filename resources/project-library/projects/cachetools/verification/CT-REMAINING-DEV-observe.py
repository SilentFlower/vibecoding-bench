"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cachetools
_candidate_source_root = root
business = False
try:
    from cachetools import TTLCache
    import pickle
    clock=[0];cache=TTLCache(3,10,timer=lambda:clock[0]);cache.update(a=1,b=2,c=3)
    before=list(cache._TTLCache__links)
    clock[0]=4
    remaining=cache.remaining('b')
    business=remaining==6 and list(cache._TTLCache__links)==before and cache.ttl==10 and cache['b']==2

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
