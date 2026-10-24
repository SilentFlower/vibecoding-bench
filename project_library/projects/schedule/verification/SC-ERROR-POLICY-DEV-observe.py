"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import schedule
_candidate_source_root = root
business = False
try:
    from schedule.policies import with_error_policy
    seen=[]
    def broken():
        raise RuntimeError('callback')
    def handler(error,count):
        seen.append((str(error),count))
        raise LookupError('handler')
    job=with_error_policy(schedule.Scheduler().every().second.do(broken),on_error=handler)
    propagated=False
    try:
        job.run()
    except LookupError:
        propagated=True
    cancel=with_error_policy(schedule.Scheduler().every().second.do(lambda:schedule.CancelJob))
    business=propagated and seen==[('callback',1)] and cancel.run() is schedule.CancelJob and cancel.consecutive_failures==0

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(schedule.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
