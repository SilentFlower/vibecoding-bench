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
    from tablib.projection import select_columns,key_token
    source=Dataset([False,0,1.0],headers=['flag','n','x']);result=select_columns(source,['x','flag'])
    business=result[0]==(1.0,False) and key_token([True])!=key_token([1]) and key_token([1])!=key_token([1.0])

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
