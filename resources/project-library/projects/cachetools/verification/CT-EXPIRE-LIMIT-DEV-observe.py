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
    clock=[0];cache=TTLCache(20,2,timer=lambda:clock[0])
    for key in range(10):
        cache[key]=key
    clock[0]=3
    removed=[]
    for limit in (0,3,2,4,5):
        batch=cache.expire(limit=limit)
        assert len(batch)<=limit
        removed.extend(batch)
    cache['live']=99
    business=removed==[(i,i) for i in range(10)] and list(cache)==['live'] and cache.currsize==1

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
