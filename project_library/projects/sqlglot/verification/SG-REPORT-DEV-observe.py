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
    from sqlglot.report import prepare_report
    result=prepare_report('WITH x AS (SELECT :n AS n) SELECT n AS total FROM x WHERE n>:threshold',values={'n':7,'threshold':2},max_rows=0,write='sqlite')
    business=result.tables==() and result.output_columns==('total',) and set(result.parameters)=={'n','threshold'} and sqlite3.connect(':memory:').execute(result.sql).fetchall()==[]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
