"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import confuse
_candidate_source_root = root
_candidate_import_bound = Path(confuse.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from datetime import date
    from decimal import Decimal
    from confuse import RootView,ConfigSource
    view=RootView([ConfigSource({'a':{'x':None},'d':date(2025,1,2),'n':Decimal('1.25')}),ConfigSource({'a':{'x':8,'y':9}})])
    view['a'].redact=True
    result=view.snapshot(redact=True)
    business=result['a']=='REDACTED' and result['d']==date(2025,1,2) and result['n']==Decimal('1.25') and view['a'].snapshot(redact=True)=='REDACTED'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
