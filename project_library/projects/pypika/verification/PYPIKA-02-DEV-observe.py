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
from pypika import Query
from pypika.terms import ExistsCriterion
business=True
for name in ('present flag','plain'):
    expression=ExistsCriterion(Query.select(2)).as_(name);sql=Query.select(expression).get_sql()
    with sqlite3.connect(':memory:') as connection:
        cursor=connection.execute(sql)
        business &= cursor.description[0][0]==name and cursor.fetchone()==(1,)
    business &= name not in expression.get_sql()

print(json.dumps({'candidate_import': Path(pypika.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
