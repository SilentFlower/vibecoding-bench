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
table=Table('records');gone=Table('gone')
sub=Query.from_(table).select(table.id).where(table.id>=4)
query=Query.with_(sub,'gone').from_(table).delete().where(table.id.isin(Query.from_(gone).select(gone.id)))
sql=query.get_sql();business &= sql.startswith('WITH gone AS ')
with sqlite3.connect(':memory:') as connection:
    connection.execute('CREATE TABLE records(id INTEGER)')
    connection.executemany('INSERT INTO records VALUES(?)',[(2,),(4,),(6,)])
    connection.execute(sql);business &= connection.execute('SELECT id FROM records').fetchall()==[(2,)]
business &= sql==query.get_sql()

print(json.dumps({'candidate_import': Path(pypika.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
