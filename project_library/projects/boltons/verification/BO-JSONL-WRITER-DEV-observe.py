"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import boltons
_candidate_source_root = root
business = False
try:
    from boltons.jsonutils import JSONLWriter
    from io import BytesIO
    from decimal import Decimal
    import json
    stream=BytesIO();writer=JSONLWriter(stream,binary=True,dumps=lambda value:json.dumps(value,ensure_ascii=False,default=str,separators=(',',':')))
    size=writer.write({'amount':Decimal('1.200'),'name':'雪'})
    class Partial:
        def write(self,value):
            return 1
    partial=JSONLWriter(Partial());failed=False
    try:
        partial.write({'a':1})
    except IOError:
        failed=True
    business=json.loads(stream.getvalue())=={'amount':'1.200','name':'雪'} and size==len(stream.getvalue()) and failed and partial.count==0

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(boltons.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
