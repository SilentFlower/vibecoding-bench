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
    from werkzeug.wrappers import Request
    from werkzeug.exceptions import NotAcceptable
    from werkzeug.negotiated_json import json_response
    failed=False
    try:
        json_response({},Request.from_values(headers={'Accept':'text/html'}))
    except NotAcceptable:
        failed=True
    result=json_response({'n':0},Request.from_values(headers={'Accept':'*/*'}),status=201)
    business=failed and result.status_code==201 and result.get_json()=={'n':0}

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
