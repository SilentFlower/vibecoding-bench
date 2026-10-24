"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import sqlglot
_candidate_source_root = root
_candidate_import_bound = Path(sqlglot.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from sqlglot.report_inspection import inspect_tables
    rows=inspect_tables('SELECT * FROM a LEFT SEMI JOIN b ON a.id=b.id',dialect='spark')
    business={row.name for row in rows}=={'a','b'} and len(rows)==2

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
