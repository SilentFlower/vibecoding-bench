"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import agate
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import pickle
business = False
try:
    anchor = datetime(2023, 12, 30, 18, 45)
    days = agate.Date(reference_datetime=anchor, locale='en_US')
    times = agate.DateTime(reference_datetime=anchor, timezone=ZoneInfo('Asia/Shanghai'), locale='en_US')
    timed = times.cast('tomorrow at 8:30am')
    restored = pickle.loads(pickle.dumps(times))
    rejected = 0
    for constructor in (agate.Date, agate.DateTime):
        for invalid in (42, date(2023, 1, 1), datetime(2023, 1, 1, tzinfo=timezone.utc)):
            try:
                constructor(reference_datetime=invalid)
            except TypeError:
                rejected += 1
    old = agate.Date().__getstate__()
    old.pop('_reference_datetime', None)
    compatible = object.__new__(agate.Date)
    compatible.__setstate__(old)
    business = (days.cast('tomorrow') == date(2023, 12, 31)
        and timed.year == 2023 and timed.month == 12 and timed.day == 31 and timed.hour == 8 and timed.minute == 30
        and timed.tzinfo == ZoneInfo('Asia/Shanghai') and restored.cast('tomorrow at 8:30am') == timed
        and rejected == 6 and compatible.cast('2031-02-03') == date(2031, 2, 3)
        and agate.DateTime(datetime_format='%Y/%m/%d %H:%M', reference_datetime=anchor).cast('2032/06/07 04:05') == datetime(2032, 6, 7, 4, 5))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(agate.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
