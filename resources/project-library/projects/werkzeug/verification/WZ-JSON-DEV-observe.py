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
    from io import BytesIO
    from werkzeug.wrappers import Request
    from werkzeug.strict_json import read_json
    class Tracked(BytesIO):
        def __init__(self,data):
            super().__init__(data);self.read_sizes=[]
        def read(self,size=-1):
            self.read_sizes.append(size);return super().read(size)
    request=Request.from_values(content_type='application/json');stream=Tracked(b'{"x":0}')
    request.environ['wsgi.input']=stream;request.environ['wsgi.input_terminated']=True;request.environ.pop('CONTENT_LENGTH',None)
    result=read_json(request,max_bytes=20)
    business=result=={'x':0} and not stream.closed and all(0<=size<=21 for size in stream.read_sizes)

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
