"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import dpath
_candidate_source_root = root
_candidate_import_bound = Path(dpath.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from dpath.transforming import transform_existing
    from dpath.walking import PathCycleError
    root={'a':[1,2],'b':3};seen=[]
    result=transform_existing(root,lambda path,value:not seen.append(path) and value+1)
    cycle={'keep':1};cycle['self']=cycle
    rejected=False
    try:
        transform_existing(cycle,lambda path,value:value+1)
    except PathCycleError:
        rejected=True
    business=result=={'a':[2,3],'b':4} and seen==[('a',0),('a',1),('b',)] and root=={'a':[1,2],'b':3} and rejected and cycle['keep']==1

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
