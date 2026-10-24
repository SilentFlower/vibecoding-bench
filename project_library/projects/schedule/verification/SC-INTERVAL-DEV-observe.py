"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import schedule
_candidate_source_root = root
business = False
try:
    from math import nan,inf
    rejected=[]
    for value in (0,-0.1,nan,inf,-inf,False,[],object()):
        try:
            schedule.Job(value)
            rejected.append(False)
        except schedule.ScheduleValueError:
            rejected.append(True)
    scheduler=schedule.Scheduler()
    job=scheduler.every(2).to(3).seconds.do(lambda:'ok')
    business=all(rejected) and job in scheduler.jobs and job.run()=='ok'

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(schedule.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
