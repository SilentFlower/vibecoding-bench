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
    from itertools import islice
    from inflect.streams import iter_join
    seen=[]
    def source():
        index=0
        while True:
            seen.append(index);yield str(index);index+=1
    parts=list(islice(iter_join(source(),sep='|'),5))
    business=''.join(parts)=='0|1|2' and len(seen)<=5

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
