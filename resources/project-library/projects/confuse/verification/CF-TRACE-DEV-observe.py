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
    from dataclasses import FrozenInstanceError
    from confuse import RootView,ConfigSource
    from confuse.trace import trace_sources
    view=RootView([ConfigSource({'v':False}),ConfigSource({'v':None})]);view['v'].redact=True
    rows=trace_sources(view['v'],include_values=True);locked=False
    try:
        rows[0].priority=9
    except FrozenInstanceError:
        locked=True
    business=locked and [row.value for row in rows]==['REDACTED','REDACTED'] and trace_sources(view['v'],include_values=True,redact=False)[0].value is False

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
