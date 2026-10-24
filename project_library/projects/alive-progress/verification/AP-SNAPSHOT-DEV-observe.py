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
    from alive_progress import alive_bar
    with alive_bar(4,disable=True) as bar:
        bar();first=bar.snapshot()
        with bar.pause():
            paused=bar.snapshot()
        bar();second=bar.snapshot()
    finished=bar.snapshot()
    business=first.count==1 and not paused.active and second.active and second.count==2 and not finished.active and finished.count==2 and first.count==1

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
