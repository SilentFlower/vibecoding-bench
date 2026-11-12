"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import werkzeug
_candidate_source_root = root
_candidate_import_bound = Path(werkzeug.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from werkzeug.exceptions import BadRequest
    from werkzeug.problems import problem_response
    result=problem_response(BadRequest('输入错误'),type='urn:validation',extensions={'errors':[{'field':'qty'}]})
    business=result.status_code==400 and result.get_json()['type']=='urn:validation' and result.get_json()['errors']==[{'field':'qty'}]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
