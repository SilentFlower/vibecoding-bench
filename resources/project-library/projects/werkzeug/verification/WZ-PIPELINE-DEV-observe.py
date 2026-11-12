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
    from werkzeug.exceptions import MethodNotAllowed
    from werkzeug.wrappers import Response
    from werkzeug.test import Client
    from werkzeug.problem_middleware import ProblemMiddleware
    from werkzeug.request_id import RequestIdMiddleware
    def app(environ,start_response):
        raise MethodNotAllowed(valid_methods=['GET'])
    response=Client(RequestIdMiddleware(ProblemMiddleware(app),factory=lambda:'req'),Response).post('/')
    business=response.status_code==405 and response.headers['Allow']=='GET' and response.get_json()['request_id']=='req' and response.headers['X-Request-ID']=='req'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
