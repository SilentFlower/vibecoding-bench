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
    from werkzeug.request_id import RequestIdMiddleware
    seen={};writer=object()
    def app(environ,start_response):
        seen['id']=environ['werkzeug.request_id'];seen['writer']=start_response('200 OK',[('X-Test','one'),('X-Test','two')]);return [b'ok']
    def begin(status,headers):
        seen['headers']=headers;return writer
    result=RequestIdMiddleware(app,factory=lambda:'generated')({'HTTP_X_REQUEST_ID':'bad value'},begin)
    business=seen['writer'] is writer and seen['id']=='generated' and seen['headers']==[('X-Test','one'),('X-Test','two'),('X-Request-ID','generated')] and result==[b'ok']

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
