"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tablib
_candidate_source_root = root
_candidate_import_bound = Path(tablib.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from tablib import Dataset
    from tablib.dedup import deduplicate
    data=Dataset([None,1],[None,2],[False,3],[0,4],headers=['id','value'])
    result=deduplicate(data,'id',keep=False)
    business=list(result)==[(False,3),(0,4)] and data.height==4

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
