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
    from decimal import Decimal
    from simplejson.strict import strict_loads
    rejected=False
    try:
        strict_loads('[{"x":0,"x":false}]')
    except ValueError:
        rejected=True
    business=rejected and strict_loads('1e999',use_decimal=True)==Decimal('1e999') and strict_loads('null') is None

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
