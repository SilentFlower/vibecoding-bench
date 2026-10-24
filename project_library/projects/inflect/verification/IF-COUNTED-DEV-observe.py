"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import inflect
_candidate_source_root = root
_candidate_import_bound = Path(inflect.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from copy import deepcopy
    from inflect import engine
    from inflect.counted import counted
    target=engine();target.num(7);before=deepcopy(target.__dict__)
    result=counted(target,'mouse',12,words=True)
    business=result=='twelve mice' and target.__dict__==before

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
