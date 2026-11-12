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
    from dpath.keymerge import merge_by_key
    left=[{'id':None,'a':{'keep':1},'items':[1]}];right=[{'id':None,'a':{'extra':2},'items':[2]}]
    result=merge_by_key(iter(left),iter(right),'id')
    business=result==[{'id':None,'a':{'keep':1,'extra':2},'items':[2]}] and left[0]['items']==[1] and right[0]['items']==[2]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
