"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import boltons
_candidate_source_root = root
business = False
try:
    from datetime import datetime,tzinfo,timedelta,timezone
    from boltons.timeutils import dt_to_timestamp
    class FoldZone(tzinfo):
        def __bool__(self):
            return False
        def utcoffset(self,value):
            return timedelta(hours=1 if value.fold else 2)
        def dst(self,value):
            return timedelta(0)
    first=datetime(2026,10,25,2,30,tzinfo=FoldZone(),fold=0)
    second=first.replace(fold=1)
    business=dt_to_timestamp(second)-dt_to_timestamp(first)==3600 and dt_to_timestamp(first)==first.timestamp()

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(boltons.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
