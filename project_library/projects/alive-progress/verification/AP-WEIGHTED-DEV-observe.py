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
    from alive_progress.weighted import alive_weighted_it
    seen=[]
    def source():
        yield ('first',4)
        yield ('second',1)
        raise LookupError('synthetic')
    failed=False
    try:
        list(alive_weighted_it(source(),lambda value:value[1],total=5,disable=True,finalize=lambda bar:seen.append(bar.snapshot())))
    except LookupError:
        failed=True
    business=failed and seen==[]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
