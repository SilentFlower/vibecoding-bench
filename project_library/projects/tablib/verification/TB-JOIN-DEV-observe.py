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
    from tablib.joining import join
    left=Dataset(headers=['id','a']);left.append(['x',[1]],tags=['left'])
    right=Dataset(headers=['id','b']);right.append(['x',False],tags=['right'])
    result=join(left,right,'id');result[0][1].append(2)
    business=left[0][1]==[1] and result.filter('left').height==1 and result.filter('right').height==1 and result[0][2] is False

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
