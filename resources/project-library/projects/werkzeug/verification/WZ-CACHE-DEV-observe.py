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
    from werkzeug.conditional_json import cacheable_json
    first=cacheable_json({'v':False},Request.from_values());etag=first.headers['ETag']
    weak=cacheable_json({'v':False},Request.from_values(headers={'If-None-Match':'W/'+etag}))
    business=weak.status_code==304 and 'Accept' in weak.vary

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
