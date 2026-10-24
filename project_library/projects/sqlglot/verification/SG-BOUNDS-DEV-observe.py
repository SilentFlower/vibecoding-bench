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
    import sqlite3
    from sqlglot.report_bounds import bounded_query
    source='WITH x AS (SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3) SELECT n FROM x ORDER BY n DESC'
    result=bounded_query(source,2,offset=1)
    business=sqlite3.connect(':memory:').execute(result.sql(dialect='sqlite')).fetchall()==[(2,),(1,)]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
