"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import xlsxwriter
_candidate_source_root = root
_candidate_import_bound = Path(xlsxwriter.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    from xlsxwriter.utc import as_utc
    first=datetime(2025,11,2,1,30,tzinfo=ZoneInfo('America/New_York'),fold=0)
    second=first.replace(fold=1)
    business=(as_utc(second)-as_utc(first)).total_seconds()==3600 and as_utc(first)==datetime(2025,11,2,5,30)

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
