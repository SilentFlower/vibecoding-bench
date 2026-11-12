"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cachetools
_candidate_source_root = root
business = False
try:
    from cachetools import LFUCache,RRCache,Cache
    cache=LFUCache(3);cache['a']=1;cache['b']=2;cache['c']=3
    cache['a'];cache['a'];cache['b']
    removed=cache.resize(2)
    grew=cache.resize(float('inf'))
    random_cache=RRCache(3,choice=lambda values:values[0]);random_cache.update(a=1,b=2,c=3)
    evicted=random_cache.resize(1)
    business=removed==( ('c',3),) and grew==() and cache.maxsize==float('inf') and len(evicted)==2 and len(random_cache)==1

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
