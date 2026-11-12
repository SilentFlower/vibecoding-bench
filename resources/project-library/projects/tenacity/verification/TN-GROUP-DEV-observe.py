"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tenacity
_candidate_source_root = root
business = False
try:
    from tenacity.retry import retry_if_exception_group,retry_if_result
    from tenacity import Retrying,RetryCallState,Future
    first=TimeoutError('one');second=KeyboardInterrupt()
    group=BaseExceptionGroup('mixed',[first,BaseExceptionGroup('fatal',[second])])
    state=RetryCallState(Retrying(),None,(),{});state.outcome=Future.construct(1,group,True)
    all_policy=retry_if_exception_group(lambda e:isinstance(e,Exception))
    any_policy=retry_if_exception_group(lambda e:isinstance(e,TimeoutError),mode='any')
    business=not all_policy(state) and any_policy(state) and (any_policy | retry_if_result(lambda value:False))(state) and state.outcome.exception() is group

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tenacity.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
