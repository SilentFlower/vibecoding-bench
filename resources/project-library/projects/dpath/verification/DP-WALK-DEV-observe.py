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
    from dpath.walking import walk_paths,PathCycleError
    data={'a':{'x':1},'b':[2]}
    paths=[path for path,value in walk_paths(data,include_containers=True,max_nodes=5,max_depth=2)]
    business=paths==[(),('a',),('a','x'),('b',),('b',0)] and list(walk_paths(3,max_nodes=1))==[((),3)]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
