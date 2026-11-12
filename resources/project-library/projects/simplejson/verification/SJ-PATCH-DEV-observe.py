"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import simplejson
_candidate_source_root = root
_candidate_import_bound = Path(simplejson.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from simplejson.patch import apply_patch
    value={'a/b':[{'n':1}]}
    result=apply_patch(value,[{'op':'replace','path':'/a~1b/0/n','value':2},{'op':'test','path':'/a~1b/0/n','value':2.0}])
    business=result=={'a/b':[{'n':2}]} and value=={'a/b':[{'n':1}]}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
