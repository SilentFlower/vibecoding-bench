"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import schedule
_candidate_source_root = root
business = False
try:
    import datetime
    events=[];scheduler=schedule.Scheduler()
    def first():
        events.append('first')
        scheduler.every().day.do(events.append,'new').set_priority(100)
    jobs=[scheduler.every().day.do(events.append,'second'), scheduler.every().day.do(first).set_priority(10)]
    for job in jobs:
        job.next_run=datetime.datetime(2020,1,1)
    scheduler.run_pending()
    business=events==['first','second'] and len(scheduler.jobs)==3

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(schedule.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
