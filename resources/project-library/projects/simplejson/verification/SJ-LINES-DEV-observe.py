"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import simplejson
_candidate_source_root = root
_candidate_import_bound = Path(simplejson.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from io import StringIO
    from decimal import Decimal
    from simplejson.lines import iterloads,dump
    rows=list(iterloads(['1.250\n','NaN\n','null\n'],errors='collect',use_decimal=True));stream=StringIO()
    count=dump([rows[0].value,rows[2].value],stream)
    business=rows[0].value==Decimal('1.250') and rows[1].status=='error' and count==2 and stream.getvalue()=='1.250\nnull\n'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
