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
    from sqlglot.report_remap import remap_tables
    connection=sqlite3.connect(':memory:');connection.execute('create table new_table(id integer)');connection.execute('insert into new_table values(9)')
    result=remap_tables('SELECT main.old_table.id FROM main.old_table',{('','main','old_table'):('','main','new_table')})
    business=connection.execute(result.sql(dialect='sqlite')).fetchall()==[(9,)]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
