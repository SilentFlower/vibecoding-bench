"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import boltons
_candidate_source_root = root
business = False
try:
    from boltons.jsonutils import JSONLIterator
    from io import StringIO
    seen=[]
    class Decoder:
        def __bool__(self):
            return False
        def __call__(self,line):
            seen.append(line)
            if line.strip()=='bad':
                raise LookupError('synthetic')
            return ('record',line.strip())
    stream=StringIO('one\nbad\ntwo\n')
    rows=list(JSONLIterator(stream,loads=Decoder(),ignore_errors=True))
    business=rows==[('record','one'),('record','two')] and len(seen)==3 and not stream.closed

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(boltons.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
