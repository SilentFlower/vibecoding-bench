"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import arrow
_candidate_source_root = root
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
business = False
try:
    start = arrow.get(datetime(2025,10,26,2,59,59,999999,tzinfo=ZoneInfo('Europe/Berlin'),fold=0))
    end = start.shift_elapsed(microseconds=1)
    other = start.to('UTC').datetime
    invalid = False
    try:
        start.shift_elapsed(seconds=float('nan'))
    except ValueError:
        invalid = True
    business = (end.fold == 1 and end.hour == 2 and end.minute == 0 and end.microsecond == 0
        and end.elapsed(start) == timedelta(microseconds=1) and start.elapsed(other) == timedelta(0)
        and start.shift_elapsed(days=-2).elapsed(start) == timedelta(days=-2) and invalid)
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(arrow.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
