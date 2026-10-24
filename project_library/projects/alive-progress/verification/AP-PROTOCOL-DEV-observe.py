"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import alive_progress
_candidate_source_root = root
_candidate_import_bound = Path(alive_progress.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    adapter=alive_progress.alive_it([],disable=True)
    before=getattr(adapter,'__deepcopy__',None)
    unknown=getattr(adapter,'_unknown_internal',False)
    finished=list(adapter)
    business=before is None and unknown is False and finished==[] and adapter.current==0 and not hasattr(adapter,'unknown_after_start')

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
