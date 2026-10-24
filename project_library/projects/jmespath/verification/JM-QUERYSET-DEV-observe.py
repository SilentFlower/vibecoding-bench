"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import jmespath
_candidate_source_root = root
_candidate_import_bound = Path(jmespath.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from jmespath.queries import QuerySet
    queries=QuerySet({'bad':'merge(first,second,third)','good':'value'},errors='collect')
    result=queries.search({'first':{},'second':{},'third':'not an object','value':9})
    business=result['bad'].status=='error' and result['bad'].error_type=='JMESPathTypeError' and result['good'].value==9

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
