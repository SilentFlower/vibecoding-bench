"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tenacity
_candidate_source_root = root
business = False
try:
    from tenacity.stop import stop_before_idle_budget
    from tenacity import Retrying,wait_fixed,RetryError
    from types import SimpleNamespace
    policy=stop_before_idle_budget(3)
    first=policy(SimpleNamespace(idle_for=0,upcoming_sleep=2))
    second=policy(SimpleNamespace(idle_for=2,upcoming_sleep=2))
    sleeps=[]
    def fail():
        raise ValueError()
    for _ in range(2):
        try:
            Retrying(wait=wait_fixed(2),stop=policy,sleep=sleeps.append)(fail)
        except RetryError:
            pass
    business=not first and second and sleeps==[2,2]

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tenacity.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
