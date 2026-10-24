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
    from dpath.patches import apply_edits
    root={1:{'value':2},'1':[3,4]}
    result=apply_edits(root,iter([{'op':'test','path':[1,'value'],'value':2},{'op':'add','path':['1',2],'value':5},{'op':'remove','path':[1,'value']}]))
    business=result=={1:{},'1':[3,4,5]} and root=={1:{'value':2},'1':[3,4]}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
