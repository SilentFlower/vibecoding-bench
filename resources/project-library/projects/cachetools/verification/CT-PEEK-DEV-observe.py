"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import cachetools
_candidate_source_root = root
business = False
try:
    from cachetools import LRUCache,TTLCache,TLRUCache
    clock=[0]
    cache=TLRUCache(4,ttu=lambda key,value,now:now+value,timer=lambda:clock[0])
    cache['short']=1;cache['long']=5;clock[0]=2
    business=cache.peek('short','missing')=='missing' and cache.peek('long')==5
    weighted=LRUCache(5,getsizeof=len);weighted['a']='xx';weighted['b']='yyy'
    weighted.peek('a');weighted['c']='z'
    business=business and 'a' not in weighted and weighted.currsize==4

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(cachetools.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
