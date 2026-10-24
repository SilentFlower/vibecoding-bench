"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import schedule
_candidate_source_root = root
business = False
try:
    from unittest.mock import patch
    import datetime
    class Fixed(datetime.datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,10,26,9,0)
    with patch.object(schedule.datetime,'datetime',Fixed):
        scheduler=schedule.Scheduler()
        job=scheduler.every().day.on_weekdays(0,2).at('09:00').do(lambda:None)
        ordinary=scheduler.every().day.at('09:00').do(lambda:None)
    business=job.next_run==datetime.datetime(2026,10,28,9,0) and ordinary.next_run==datetime.datetime(2026,10,27,9,0)

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(schedule.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
