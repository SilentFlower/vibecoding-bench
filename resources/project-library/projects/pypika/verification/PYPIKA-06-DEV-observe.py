"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['pypika']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import pypika
import sqlite3
from pypika import Query,Table
business=True
table=Table('sample');expression=((table.left==1)|(table.right==1)).isnotnull()
sql=Query.from_(table).select(table.id).where(expression).get_sql()
business &= '("left"=1 OR "right"=1) IS NOT NULL' in sql
with sqlite3.connect(':memory:') as connection:
    connection.execute('CREATE TABLE sample(id INTEGER,left INTEGER,right INTEGER)')
    connection.executemany('INSERT INTO sample VALUES(?,?,?)',[(1,1,None),(2,None,0),(3,0,0)])
    business &= connection.execute(sql).fetchall()==[(1,),(3,)]
business &= table.left.isnull().get_sql()=='left IS NULL'

print(json.dumps({'candidate_import': Path(pypika.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
