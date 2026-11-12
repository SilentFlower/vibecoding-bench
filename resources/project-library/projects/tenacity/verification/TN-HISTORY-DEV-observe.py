"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tenacity
_candidate_source_root = root
business = False
try:
    from tenacity.history import RetryHistory
    from concurrent.futures import ThreadPoolExecutor
    history=RetryHistory(7)
    wrapped=history.wrap(lambda value:value*2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(wrapped,range(20)))
    records=history.records
    unique=len({r.sequence for r in records})==7
    frozen=False
    try:
        records[0].succeeded=False
    except (AttributeError,TypeError):
        frozen=True
    business=results==[i*2 for i in range(20)] and len(records)==7 and unique and frozen and all(r.succeeded for r in records)

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tenacity.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
