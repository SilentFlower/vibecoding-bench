"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tenacity
_candidate_source_root = root
business = False
try:
    from tenacity.wait import wait_random,wait_random_exponential,wait_exponential_jitter
    from types import SimpleNamespace
    from unittest.mock import patch
    class Source:
        def random(self):
            return 0.75
        def uniform(self,low,high):
            return high
    state=SimpleNamespace(attempt_number=1000000)
    source=Source()
    with patch('random.random',side_effect=AssertionError('不应消耗全局源')),patch('random.uniform',side_effect=AssertionError('不应消耗全局源')):
        business=(wait_random(1,5,random_source=source)(state)==4
            and wait_random_exponential(multiplier=1,max=7,random_source=source)(state)==7
            and wait_exponential_jitter(multiplier=1,max=9,random_source=source)(state)==9)

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tenacity.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
