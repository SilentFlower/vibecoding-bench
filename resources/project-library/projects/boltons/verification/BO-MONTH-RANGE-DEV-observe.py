"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import boltons
_candidate_source_root = root
business = False
try:
    from boltons.timeutils import month_range
    from datetime import date
    forward=list(month_range(date(2024,1,30),date(2024,7,30),2,inclusive=True))
    reverse=list(month_range(date(2024,7,30),date(2024,1,30),-2,inclusive=False))
    business=forward==[date(2024,1,30),date(2024,3,30),date(2024,5,30),date(2024,7,30)] and reverse==[date(2024,7,30),date(2024,5,30),date(2024,3,30)]

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(boltons.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
