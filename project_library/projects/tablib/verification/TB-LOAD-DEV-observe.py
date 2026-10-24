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
    from tablib.loading import load_records
    records=[{'b':2,'a':1},{'a':3,'b':4}]
    result=load_records(records,['a','b'])
    business=list(result.dataset)==[(1,2),(3,4)] and result.dataset.dict==[{'a':1,'b':2},{'a':3,'b':4}] and records[0]=={'b':2,'a':1}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
